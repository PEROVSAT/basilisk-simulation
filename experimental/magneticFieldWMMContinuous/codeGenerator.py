import sympy as sp
from sympy.printing.c import ccode

def generate_wmm_jacobian():
    print("Generating SymPy C++ Code for WMM Jacobian...\n")

    # 1. Define Cartesian coordinates as real variables
    x, y, z = sp.symbols('x y z', real=True)

    # 2. Define Spherical mappings
    r = sp.sqrt(x**2 + y**2 + z**2)
    theta = sp.acos(z / r)
    phi = sp.atan2(y, x)

    # 3. Define V as an abstract function of the spherical coordinates
    V = sp.Function('V')(r, theta, phi)

    # 4. Compute Cartesian B-field components (B = -nabla V)
    print("Computing first derivatives (B-field)...")
    Bx = -sp.diff(V, x)
    By = -sp.diff(V, y)
    Bz = -sp.diff(V, z)

    # 5. Compute the symmetric Jacobian (Hessian of V)
    # We only need 6 of the 9 components because the Hessian is symmetric (Jxy = Jyx)
    print("Computing second derivatives (Jacobian/Hessian)...")
    Jxx = sp.diff(Bx, x)
    Jxy = sp.diff(Bx, y)
    Jxz = sp.diff(Bx, z)
    Jyy = sp.diff(By, y)
    Jyz = sp.diff(By, z)
    Jzz = sp.diff(Bz, z)

    # 6. Clean up the output for C++ by substituting SymPy's abstract 
    # Derivative() notation with clean C++ variable names.
    
    # Create the target C++ symbols
    subs_dict = {
        sp.Derivative(V, r, r): sp.Symbol('d2V_dr2'),
        sp.Derivative(V, theta, theta): sp.Symbol('d2V_dtheta2'),
        sp.Derivative(V, phi, phi): sp.Symbol('d2V_dphi2'),
        sp.Derivative(V, r, theta): sp.Symbol('d2V_dr_dtheta'),
        sp.Derivative(V, r, phi): sp.Symbol('d2V_dr_dphi'),
        sp.Derivative(V, theta, phi): sp.Symbol('d2V_dtheta_dphi'),
        sp.Derivative(V, r): sp.Symbol('dV_dr'),
        sp.Derivative(V, theta): sp.Symbol('dV_dtheta'),
        sp.Derivative(V, phi): sp.Symbol('dV_dphi')
    }

    # Apply substitutions and simplify
    def process_expr(expr):
        return sp.simplify(expr.subs(subs_dict))

    Jxx_c = process_expr(Jxx)
    Jxy_c = process_expr(Jxy)
    Jxz_c = process_expr(Jxz)
    Jyy_c = process_expr(Jyy)
    Jyz_c = process_expr(Jyz)
    Jzz_c = process_expr(Jzz)

    # 7. Print the resulting C++ Code
    print("\n// --- COPY BELOW INTO Basilisk C++ --- //")
    print(f"gradB_N[0][0] = {ccode(Jxx_c)};")
    print(f"gradB_N[0][1] = {ccode(Jxy_c)};")
    print(f"gradB_N[0][2] = {ccode(Jxz_c)};")
    print(f"gradB_N[1][0] = gradB_N[0][1]; // Symmetric")
    print(f"gradB_N[1][1] = {ccode(Jyy_c)};")
    print(f"gradB_N[1][2] = {ccode(Jyz_c)};")
    print(f"gradB_N[2][0] = gradB_N[0][2]; // Symmetric")
    print(f"gradB_N[2][1] = gradB_N[1][2]; // Symmetric")
    print(f"gradB_N[2][2] = {ccode(Jzz_c)};")

if __name__ == "__main__":
    generate_wmm_jacobian()