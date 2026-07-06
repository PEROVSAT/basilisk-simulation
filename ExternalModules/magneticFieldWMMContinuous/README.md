# Continuous Implementation of the World Magnetic Model

## Motivation
While attempting to make a continuous implementation of Hysteresis rods, the existing `magneticFieldWMM` module was one of the remaining sources of non-continuous points. The default approach evaluates the magnetic field discretely at the task rate, creating a Zero-Order Hold (ZOH) signal. Differentiating a ZOH signal via finite difference produces mathematical impulses (spikes followed by zeros), which forces stiff ODE solvers—such as those required for Jiles-Atherton hysteresis equations—to stall or fail. Given that the WMM itself is constructed from continuous, differentiable functions, an analytical calculation of $\dot{\mathbf{B}}$ allows for stable, larger integration timesteps and a physically accurate simulation environment.

## Math

### 1. The WMM Scalar Potential
The World Magnetic Model represents the Earth's main magnetic field as the negative spatial gradient of a scalar magnetic potential, $V$. This potential is defined in spherical coordinates $(r, \theta, \phi)$ by a spherical harmonic expansion up to degree and order 12:

$$V(r, \theta, \phi, t) = R_e \sum_{n=1}^{12} \left(\frac{R_e}{r}\right)^{n+1} \sum_{m=0}^{n} \left[ g_n^m(t) \cos(m\phi) + h_n^m(t) \sin(m\phi) \right] P_n^m(\cos\theta)$$

Where:
* $R_e$ is the geomagnetic reference radius.
* $r, \theta, \phi$ are the radial distance, co-latitude, and longitude.
* $g_n^m(t)$ and $h_n^m(t)$ are time-dependent Gauss coefficients.
* $P_n^m$ are the Schmidt semi-normalized associated Legendre functions.

The local magnetic field vector $\mathbf{B}$ is the continuous first spatial derivative of this potential:

$$\mathbf{B} = -\nabla V$$

### 2. The Material Derivative of the Magnetic Field
Because the spacecraft moves through this spatially varying field, the true rate of change of the magnetic field experienced by the vehicle is the total (or material) derivative, which applies the multivariable chain rule:

$$\frac{d\mathbf{B}}{dt} = \frac{\partial \mathbf{B}}{\partial t} + (\mathbf{v} \cdot \nabla)\mathbf{B}$$

* $\frac{\partial \mathbf{B}}{\partial t}$ represents the explicit secular variation of the field over time (driven by the slow change of the Gauss coefficients). For the timescale of typical orbit simulations, $\frac{\partial \mathbf{B}}{\partial t} \approx 0$.
* $\mathbf{v}$ is the spacecraft's inertial velocity vector in Cartesian coordinates $(\frac{dx}{dt}, \frac{dy}{dt}, \frac{dz}{dt})$.
* $\nabla\mathbf{B}$ is the spatial gradient tensor (Jacobian matrix) of the magnetic field.

By dropping the negligible secular variation, the continuous rate of change becomes a direct matrix-vector product:

$$\dot{\mathbf{B}} = [\nabla\mathbf{B}] \mathbf{v}$$

### 3. The Spatial Gradient Tensor (Jacobian/Hessian)
To evaluate $[\nabla\mathbf{B}]$, we must compute the spatial derivatives of $\mathbf{B}$ with respect to the Cartesian inertial frame $(x, y, z)$. Because $\mathbf{B} = -\nabla V$, the $3 \times 3$ Jacobian of $\mathbf{B}$ is mathematically equivalent to the negative **Hessian matrix** of the scalar potential $V$.

$$[\nabla\mathbf{B}] = \begin{bmatrix} \frac{\partial B_x}{\partial x} & \frac{\partial B_x}{\partial y} & \frac{\partial B_x}{\partial z} \\ \frac{\partial B_y}{\partial x} & \frac{\partial B_y}{\partial y} & \frac{\partial B_y}{\partial z} \\ \frac{\partial B_z}{\partial x} & \frac{\partial B_z}{\partial y} & \frac{\partial B_z}{\partial z} \end{bmatrix}$$

### 4. Coordinate Transformation and Chain Rule
A fundamental computational challenge arises from coordinate system mismatch: $V$ is defined in spherical coordinates $(r, \theta, \phi)$, while the spacecraft velocity $\mathbf{v}$ and the required $[\nabla\mathbf{B}]$ matrix operate in Cartesian coordinates $(x, y, z)$. 

Constructing the Jacobian requires bridging these systems using the multivariable chain rule. For example, computing the change in the radial field component $B_r$ with respect to the Cartesian $x$-axis requires mapping the partial derivatives:

$$\frac{\partial B_r}{\partial x} = \frac{\partial B_r}{\partial r}\frac{\partial r}{\partial x} + \frac{\partial B_r}{\partial \theta}\frac{\partial \theta}{\partial x} + \frac{\partial B_r}{\partial \phi}\frac{\partial \phi}{\partial x}$$

This chain rule expansion must be applied to all 9 components of the Jacobian tensor. The resulting system requires taking the second spatial derivatives of the associated Legendre polynomials and the 144-term harmonic expansion. In practice, evaluating this analytically in C++ will bypass finite difference approximations, providing the stiff ODE solver with a mathematically exact, perfectly smooth $\dot{\mathbf{B}}$ driven purely by the spacecraft's continuous inertial velocity.