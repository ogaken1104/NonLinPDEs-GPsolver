# JAX
from functools import partial

import jax.numpy as jnp
import jax.ops as jop
from jax import grad, hessian, jit, vmap
from jax.config import config

config.update("jax_enable_x64", True)

import sys

# numpy
import numpy as onp
from numpy import random

# from src.Gram_matrice import Gram_matrix_assembly, construct_Theta_test
from src.sample_points import sampled_pts_grid, sampled_pts_rdm
from .Gram_matrice_new import Gram_matrix_assembly, construct_Theta_test


class Burgers(object):
    def __init__(
        self, alpha=1.0, nu=0.2, bdy=None, rhs=None, domain=onp.array([[0, 1], [-1, 1]])
    ):
        # default u_t+\alpha u u_x-\nu u_{xx}=0, x \in [-1,1], t \in [0,1] so domain (t,x) in [0,1]*[-1,1]
        self.alpha = alpha
        self.nu = nu
        self.bdy = bdy
        self.rhs = rhs
        self.domain = domain

    @partial(jit, static_argnums=(0,))
    def get_bd(self, x1, x2):
        return self.bdy(x1, x2)

    @partial(jit, static_argnums=(0,))
    def get_rhs(self, x1, x2):
        return self.rhs(x1, x2)

    def sampled_pts(self, N_domain, N_boundary, sampled_type="random"):
        # if rdm is true, sample points uniformly randomly, else in a uniform grid
        if sampled_type == "random":
            X_domain, X_boundary = sampled_pts_rdm(
                N_domain, N_boundary, self.domain, time_dependent=True
            )
        elif sampled_type == "grid":
            X_domain, X_boundary = sampled_pts_grid(
                N_domain, N_boundary, self.domain, time_dependent=True
            )
        self.X_domain = X_domain
        self.N_domain = X_domain.shape[0]
        self.X_boundary = X_boundary
        self.N_boundary = X_boundary.shape[0]
        self.rhs_f = vmap(self.get_rhs)(X_domain[:, 0], X_domain[:, 1])
        self.bdy_g = vmap(self.get_bd)(X_boundary[:, 0], X_boundary[:, 1])

    # directly given sampled points
    def get_sampled_points(self, X_domain, X_boundary):
        self.X_domain = X_domain
        self.N_domain = X_domain.shape[0]
        self.X_boundary = X_boundary
        self.N_boundary = X_boundary.shape[0]
        self.rhs_f = vmap(self.get_rhs)(X_domain[:, 0], X_domain[:, 1])
        self.bdy_g = vmap(self.get_bd)(X_boundary[:, 0], X_boundary[:, 1])

    def Gram_matrix(
        self,
        kernel="anisotropic_Gaussian",
        kernel_parameter=[1 / 3, 1 / 20],
        nugget=1e-5,
        nugget_type="adaptive",
    ):
        Theta = Gram_matrix_assembly(
            self.X_domain,
            self.X_boundary,
            eqn="Burgers",
            kernel=kernel,
            kernel_parameter=kernel_parameter,
        )
        self.nugget_type = nugget_type
        self.nugget = nugget
        self.kernel = kernel
        self.kernel_parameter = kernel_parameter
        if nugget_type == "adaptive":
            # calculate trace
            trace1 = jnp.trace(Theta[: self.N_domain, : self.N_domain])
            trace2 = jnp.trace(
                Theta[
                    self.N_domain : 2 * self.N_domain, self.N_domain : 2 * self.N_domain
                ]
            )
            trace4 = jnp.trace(Theta[3 * self.N_domain :, 3 * self.N_domain :])
            ratio = [trace1 / trace4, trace2 / trace4]
            self.ratio = ratio
            temp = jnp.concatenate(
                (
                    ratio[0] * jnp.ones((1, self.N_domain)),
                    ratio[1] * jnp.ones((1, self.N_domain)),
                    jnp.ones((1, self.N_domain + self.N_boundary)),
                ),
                axis=1,
            )
            self.Theta = Theta + nugget * jnp.diag(temp[0])
        elif nugget_type == "identity":
            self.Theta = Theta + nugget * jnp.eye(3 * self.N_domain + self.N_boundary)
        elif nugget_type == "none":
            self.Theta = Theta

    def Gram_Cholesky(self):
        try:
            self.L = jnp.linalg.cholesky(self.Theta)
        except:
            print("[Error] Cholesky factorization failed: maybe nugget is too small!")
            sys.exit()

    @partial(jit, static_argnums=(0,))
    def loss(self, z):
        v0 = z[: self.N_domain]
        v2 = z[self.N_domain : 2 * self.N_domain]

        vv = jnp.append(self.rhs_f - self.alpha * v0 * v2, v2)
        vv = jnp.append(vv, v0)
        vv = jnp.append(vv, self.bdy_g)
        temp = jnp.linalg.solve(self.L, vv)
        return jnp.dot(temp, temp)

    @partial(jit, static_argnums=(0,))
    def grad_loss(self, z):
        return grad(self.loss)(z)

    @partial(jit, static_argnums=(0,))
    def Hessian_GN(self, z):
        v0 = z[: self.N_domain]
        v2 = z[self.N_domain : 2 * self.N_domain]

        mtx = jnp.zeros((3 * self.N_domain + self.N_boundary, 2 * self.N_domain))
        mtx1 = jnp.concatenate(
            (
                -self.alpha * jnp.diag(v2),
                -self.alpha * jnp.diag(v0),
            ),
            axis=1,
        )
        mtx = mtx.at[0 : self.N_domain, :].set(mtx1)
        mtx = mtx.at[
            self.N_domain : 2 * self.N_domain, self.N_domain : 2 * self.N_domain
        ].set(jnp.eye(self.N_domain))
        mtx = mtx.at[2 * self.N_domain : 3 * self.N_domain, : self.N_domain].set(
            jnp.eye(self.N_domain)
        )
        ss = jnp.linalg.solve(self.L, mtx)
        return 2 * jnp.matmul(jnp.transpose(ss), ss)

    def GN_method(self, max_iter=10, step_size=1, initial_sol="rdm", print_hist=True):
        if initial_sol == "rdm":
            sol = random.normal(0.0, 1.0, (2 * self.N_domain))
        self.init_sol = sol
        loss_hist = []  # history of loss function values
        loss_now = self.loss(sol)
        if jnp.isnan(loss_now):
            print("[Error] Loss is nan: maybe nugget is too small!")
            # sys.exit()
        loss_hist.append(loss_now)

        if print_hist:
            print("iter = 0", "Loss =", loss_now)  # print out history

        for iter_step in range(1, max_iter + 1):
            temp = jnp.linalg.solve(self.Hessian_GN(sol), self.grad_loss(sol))
            sol = sol - step_size * temp
            loss_now = self.loss(sol)
            if jnp.isnan(loss_now):
                print("[Error] Loss is nan: maybe nugget is too small!")
                # sys.exit()
            loss_hist.append(loss_now)
            if print_hist:
                # print out history
                print(
                    "iter = ",
                    iter_step,
                    "Gauss-Newton step size =",
                    step_size,
                    " Loss = ",
                    loss_now,
                )
        self.max_iter = max_iter
        self.step_size = step_size
        self.loss_hist = loss_hist

        v0 = sol[: self.N_domain]
        v2 = sol[self.N_domain : 2 * self.N_domain]
        sol_vec = jnp.concatenate(
            (self.rhs_f - self.alpha * v0 * v2, v2, v0, self.bdy_g),
            axis=0,
        )
        self.sol_vec = sol_vec
        self.sol_sampled_pts = v0

    def extend_sol(self, X_test):
        Theta_test = construct_Theta_test(
            X_test,
            self.X_domain,
            self.X_boundary,
            eqn="Burgers",
            kernel=self.kernel,
            kernel_parameter=self.kernel_parameter,
        )
        temp = jnp.linalg.solve(
            jnp.transpose(self.L), jnp.linalg.solve(self.L, self.sol_vec)
        )
        self.X_test = X_test
        self.N_test = X_test.shape[0]
        self.extended_sol = jnp.matmul(Theta_test, temp)
