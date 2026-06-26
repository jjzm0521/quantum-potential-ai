"""
Exportadores de resultados:
  - CSV de eigenvalores
  - NumPy .npz con funciones de onda
  - Script MATLAB/COMSOL LiveLink (.m)
"""

from __future__ import annotations
import io
import textwrap
import numpy as np
from datetime import datetime
from .solver import SolverResult
from .solver_1d import SolverResult1D


def _param_unit(name: str) -> str:
    n = name.lower()
    if n in {"n", "k", "cycles", "ciclos", "nfoot", "nshape", "nexp"}:
        return ""
    if n in {"theta", "phi"} or "angle" in n or n.endswith("deg"):
        return "deg"
    if n.startswith("v") or any(t in n for t in ("depth", "amp", "height", "value", "pot", "barrier")):
        return "eV"
    return "nm"


def _comsol_param_set_lines(params: dict) -> str:
    lines = []
    for key, value in params.items():
        if key in {"L_nm", "N", "material"}:
            continue
        if isinstance(value, (int, float)):
            unit = _param_unit(key)
            expr = f"{value}[{unit}]" if unit else f"{value}"
        else:
            expr = str(value)
        lines.append(f"model.param.set('{key}', '{expr}');")
    return "\n        ".join(lines) if lines else "% Sin parámetros de diseño adicionales."


def to_csv(result) -> bytes:
    """Eigenvalores en CSV. Acepta SolverResult o SolverResult1D."""
    buf = io.StringIO()
    buf.write("# Quantum Potential AI — eigenvalores\n")
    buf.write(f"# Fecha: {datetime.now().isoformat()}\n")
    if isinstance(result, SolverResult1D):
        buf.write(f"# Dimension: 1D | N = {result.n_grid}\n")
    else:
        buf.write(f"# Dimension: 2D | Grilla: {result.grid_size[0]}x{result.grid_size[1]}\n")
    buf.write("n,E_meV\n")
    for i, E in enumerate(result.energies_meV):
        buf.write(f"{i},{E:.6f}\n")
    return buf.getvalue().encode()


def to_npz(result) -> bytes:
    """Paquete NumPy. Acepta SolverResult (2D) o SolverResult1D."""
    buf = io.BytesIO()
    if isinstance(result, SolverResult1D):
        np.savez_compressed(
            buf,
            x_nm=result.x_nm,
            V_eV=result.V_eV,
            energies_meV=result.energies_meV,
            wavefunctions=result.wavefunctions,
            prob_density=result.prob_density,
            dimension=1,
        )
    else:
        np.savez_compressed(
            buf,
            x_nm=result.x_nm,
            y_nm=result.y_nm,
            V_eV=result.V_eV,
            energies_meV=result.energies_meV,
            wavefunctions=result.wavefunctions,
            dimension=2,
        )
    return buf.getvalue()


def to_comsol_m_1d(
    result: SolverResult1D,
    pot_name: str,
    params: dict,
    material_name: str,
    m_eff: float,
    expr_str: str,
) -> bytes:
    """Script COMSOL LiveLink para problema 1D."""
    L = result.x_nm[-1] - result.x_nm[0]
    n_states = len(result.energies_meV)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    params_str = "\n".join(f"%   {k} = {v}" for k, v in params.items())

    script = textwrap.dedent(f"""\
        % ============================================================
        % Quantum Potential AI — Script COMSOL LiveLink (MATLAB) — 1D
        % Generado: {now}
        % Potencial: {pot_name}
        % Material:  {material_name}  (m* = {m_eff} m_e)
        %
        % Parámetros usados:
        {params_str}
        % ============================================================

        import com.comsol.model.*
        import com.comsol.model.util.*

        model = ModelUtil.create('QuantumModel1D');
        model.label('Quantum Potential AI - 1D');

        % --- Parámetros físicos ---
        model.param.set('hbar',  '1.054571817e-34[J*s]');
        model.param.set('m_e',   '9.10938e-31[kg]');
        model.param.set('eV',    '1.60218e-19[J]');
        model.param.set('m_eff', '{m_eff}');
        model.param.set('m_star','m_eff*m_e');
        model.param.set('L',     '{L:.1f}e-9[m]');

        % --- Geometría 1D: intervalo [-L/2, L/2] ---
        model.geom.create('geom1', 1);
        model.geom('geom1').create('i1', 'Interval');
        model.geom('geom1').feature('i1').set('p1', '-L/2');
        model.geom('geom1').feature('i1').set('p2',  'L/2');
        model.geom('geom1').run;

        % --- Función V(x) en eV (x en metros) ---
        model.func.create('V_pot', 'Analytic');
        model.func('V_pot').set('funcname', 'V_pot');
        model.func('V_pot').set('expr',     '{expr_str}');
        model.func('V_pot').set('args',     {{'x'}});
        model.func('V_pot').set('argunit',  {{'m'}});
        model.func('V_pot').set('plotargs', {{'x', '-L/2', 'L/2'}});
        model.func('V_pot').set('fununit',  'eV');

        % --- Schrödinger 1D vía CoefficientFormPDE ---
        % -d/dx(c·dψ/dx) + a·ψ = λ·d·ψ
        model.physics.create('c', 'CoefficientFormPDE', 'geom1');
        model.physics('c').field('dependentVariable').field('psi');
        model.physics('c').feature('cfeq1').set('c', 'hbar^2/(2*m_star)');
        model.physics('c').feature('cfeq1').set('a', 'V_pot(x)*eV');
        model.physics('c').feature('cfeq1').set('da', '1');

        % Dirichlet ψ=0 en los extremos
        model.physics('c').create('dir1', 'DirichletBoundary', 0);
        model.physics('c').feature('dir1').selection.all;
        model.physics('c').feature('dir1').set('r', '0');

        % --- Malla ---
        model.mesh.create('mesh1', 'geom1');
        model.mesh('mesh1').automatic(true);
        model.mesh('mesh1').autoMeshSize(2);   % Fine
        model.mesh('mesh1').run;

        % --- Eigenvalor ---
        model.study.create('std1');
        model.study('std1').create('eig', 'Eigenvalue');
        model.study('std1').feature('eig').set('neigsactive', true);
        model.study('std1').feature('eig').set('neigs', {n_states});
        model.study('std1').run;

        E_J = mphglobal(model, 'lambda', 'dataset', 'dset1');
        E_meV = real(E_J) / 1.60218e-19 * 1000;
        disp('Eigenvalores (meV):');
        disp(E_meV');

        mphsave(model, 'quantum_model_1d.mph');
        disp('Modelo guardado en quantum_model_1d.mph');
    """)
    return script.encode()


def to_comsol_m(
    result: SolverResult,
    pot_name: str,
    params: dict,
    material_name: str,
    m_eff: float,
    expr_str: str,
) -> bytes:
    """
    Genera script MATLAB (COMSOL LiveLink) que define:
      - geometría rectangular
      - potencial V(x,y) como función analítica
      - ecuación de Schrödinger vía CoefficientFormPDE
      - mesh adaptativo
      - solver de eigenvalores
    """
    Lx = result.x_nm[-1] - result.x_nm[0]
    Ly = result.y_nm[-1] - result.y_nm[0]
    n_states = len(result.energies_meV)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    params_str = "\n".join(
        f"%   {k} = {v}" for k, v in params.items()
    )
    design_params = _comsol_param_set_lines(params)

    script = textwrap.dedent(f"""\
        % ============================================================
        % Quantum Potential AI — Script COMSOL LiveLink (MATLAB)
        % Generado: {now}
        % Potencial: {pot_name}
        % Material:  {material_name}  (m* = {m_eff} m_e)
        %
        % Parámetros usados:
        {params_str}
        %
        % Uso: abrir MATLAB con LiveLink activo y ejecutar este archivo.
        % ============================================================

        import com.comsol.model.*
        import com.comsol.model.util.*

        model = ModelUtil.create('QuantumModel');
        model.label('Quantum Potential AI');

        % --- Parámetros físicos ---
        model.param.set('hbar',  '1.054571817e-34[J*s]');
        model.param.set('m_e',   '9.10938e-31[kg]');
        model.param.set('eV',    '1.60218e-19[J]');
        model.param.set('m_eff', '{m_eff}');
        model.param.set('m_star','m_eff*m_e');
        {design_params}

        % --- Dominio (nm → m) ---
        model.param.set('Lx', '{Lx:.1f}e-9[m]');
        model.param.set('Ly', '{Ly:.1f}e-9[m]');

        % --- Geometría ---
        model.geom.create('geom1', 2);
        geom = model.geom('geom1');
        r = geom.create('r1', 'Rectangle');
        r.set('width',  'Lx');
        r.set('height', 'Ly');
        r.set('base',   'center');
        geom.run;

        % --- Función analítica del potencial ---
        % V(x,y) en eV, coordenadas en metros
        model.func.create('V_pot', 'Analytic');
        model.func('V_pot').set('funcname', 'V_pot');
        model.func('V_pot').set('expr',     '{expr_str}');
        model.func('V_pot').set('args',     {{'x','y'}});
        model.func('V_pot').set('argunit',  {{'m','m'}});
        model.func('V_pot').set('plotargs', {{'x', '-Lx/2', 'Lx/2'; 'y', '-Ly/2', 'Ly/2'}});
        model.func('V_pot').set('fununit',  'eV');

        % --- Física: Ecuación de Schrödinger + energía potencial del electrón ---
        model.physics.create('schr', 'SchrodingerEquation', 'geom1');
        try
            model.physics('schr').feature('meff1').set('meff', 'm_eff');
        catch
            % El nombre de la propiedad puede variar según versión de COMSOL.
        end
        try
            model.physics('schr').feature('ve1').active(false);
        catch
            % Deshabilita el potencial por defecto si existe.
        end
        model.physics('schr').create('ve_afm', 'ElectronPotentialEnergy', 2);
        model.physics('schr').feature('ve_afm').selection.all;
        model.physics('schr').feature('ve_afm').set('Ve_src', 'userdef');
        model.physics('schr').feature('ve_afm').set('Ve', 'V_pot(x,y)');

        % --- Malla ---
        model.mesh.create('mesh1', 'geom1');
        model.mesh('mesh1').automatic(true);
        model.mesh('mesh1').autoMeshSize(3);   % 3 = Normal
        model.mesh('mesh1').run;

        % --- Estudio de eigenvalores ---
        model.study.create('std1');
        model.study('std1').create('eig', 'Eigenvalue');
        model.study('std1').feature('eig').set('neigsactive', true);
        model.study('std1').feature('eig').set('neigs', {n_states});
        model.study('std1').feature('eig').set('shift', '0');
        model.study('std1').run;

        % --- Extraer eigenvalores (en Joules → meV) ---
        E_J  = mphglobal(model, 'lambda', 'dataset', 'dset1');
        E_meV = real(E_J) / 1.60218e-19 * 1000;
        disp('Eigenvalores (meV):');
        disp(E_meV');

        % --- Guardar modelo ---
        mphsave(model, 'quantum_model.mph');
        disp('Modelo guardado en quantum_model.mph');
    """)
    return script.encode()
