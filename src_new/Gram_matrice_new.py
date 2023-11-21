# JAX
import jax.numpy as jnp
import jax.ops as jop
from jax import vmap
from jax.config import config

config.update("jax_enable_x64", True)

# numpy
import numpy as onp

from src.kernels import Anisotropic_Gaussian_kernel, Gaussian_kernel


def Gram_matrix_assembly(
    X_domain,
    X_boundary,
    eqn="Nonlinear_elliptic",
    kernel="Gaussian",
    kernel_parameter=0.2,
    nu=0.02,
):
    N_domain = X_domain.shape[0]
    N_boundary = X_boundary.shape[0]

    # introduce auxiliary values that are used to compute block interactions in the Gram matrix
    Xd0 = X_domain[:N_domain, 0]
    Xd1 = X_domain[:N_domain, 1]

    Xdb0 = jnp.concatenate([Xd0, X_boundary[:N_boundary, 0]])
    Xdb1 = jnp.concatenate([Xd1, X_boundary[:N_boundary, 1]])

    # interior -- interior interactions
    XXdd0 = jnp.transpose(jnp.tile(Xd0, (N_domain, 1)))
    XXdd1 = jnp.transpose(jnp.tile(Xd1, (N_domain, 1)))

    # interior+boudary -- interior+bpundary interactions
    XXdbdb0 = jnp.transpose(jnp.tile(Xdb0, (N_domain + N_boundary, 1)))
    XXdbdb1 = jnp.transpose(jnp.tile(Xdb1, (N_domain + N_boundary, 1)))

    # interior v.s. interior+boundary interactions
    XXddb0 = jnp.transpose(jnp.tile(Xd0, (N_domain + N_boundary, 1)))
    XXddb1 = jnp.transpose(jnp.tile(Xd1, (N_domain + N_boundary, 1)))
    XXddb0_2 = jnp.tile(Xdb0, (N_domain, 1))
    XXddb1_2 = jnp.tile(Xdb1, (N_domain, 1))

    if kernel == "Gaussian":
        K = Gaussian_kernel()
    elif kernel == "anisotropic_Gaussian":
        K = Anisotropic_Gaussian_kernel()

    if eqn == "Burgers":
        # Construct kernel matrix
        Theta = jnp.zeros((3 * N_domain + N_boundary, 3 * N_domain + N_boundary))
        # interior v.s. interior
        val = vmap(
            lambda x1, x2, y1, y2: K.D_x1_D_y1_kappa(x1, x2, y1, y2, kernel_parameter)
            - 2 * nu * K.D_x1_DD_y2_kappa(x1, x2, y1, y2, kernel_parameter)
            + nu**2 * K.DD_x2_DD_y2_kappa(x1, x2, y1, y2, kernel_parameter)
        )(
            XXdd0.flatten(),
            XXdd1.flatten(),
            jnp.transpose(XXdd0).flatten(),
            jnp.transpose(XXdd1).flatten(),
        )
        Theta = Theta.at[0:N_domain, 0:N_domain].set(
            jnp.reshape(val, (N_domain, N_domain))
        )

        val = vmap(
            lambda x1, x2, y1, y2: K.D_x1_D_y2_kappa(x1, x2, y1, y2, kernel_parameter)
            - nu * K.DD_x2_D_y2_kappa(x1, x2, y1, y2, kernel_parameter)
        )(
            XXdd0.flatten(),
            XXdd1.flatten(),
            jnp.transpose(XXdd0).flatten(),
            jnp.transpose(XXdd1).flatten(),
        )
        Theta = Theta.at[0:N_domain, N_domain : 2 * N_domain].set(
            jnp.reshape(val, (N_domain, N_domain))
        )
        Theta = Theta.at[N_domain : 2 * N_domain, 0:N_domain].set(
            jnp.transpose(jnp.reshape(val, (N_domain, N_domain)))
        )

        val = vmap(
            lambda x1, x2, y1, y2: K.D_x2_D_y2_kappa(x1, x2, y1, y2, kernel_parameter)
        )(
            XXdd0.flatten(),
            XXdd1.flatten(),
            jnp.transpose(XXdd0).flatten(),
            jnp.transpose(XXdd1).flatten(),
        )
        Theta = Theta.at[N_domain : 2 * N_domain, N_domain : 2 * N_domain].set(
            jnp.reshape(val, (N_domain, N_domain))
        )

        # interior+boundary v.s. interior+boundary
        val = vmap(lambda x1, x2, y1, y2: K.kappa(x1, x2, y1, y2, kernel_parameter))(
            XXdbdb0.flatten(),
            XXdbdb1.flatten(),
            jnp.transpose(XXdbdb0).flatten(),
            jnp.transpose(XXdbdb1).flatten(),
        )
        Theta = Theta.at[2 * N_domain :, 2 * N_domain :].set(
            jnp.reshape(val, (N_domain + N_boundary, N_domain + N_boundary))
        )

        # interior v.s. interior+boundary
        val = vmap(
            lambda x1, x2, y1, y2: K.D_x1_kappa(x1, x2, y1, y2, kernel_parameter)
            - nu * K.DD_x2_kappa(x1, x2, y1, y2, kernel_parameter)
        )(XXddb0.flatten(), XXddb1.flatten(), XXddb0_2.flatten(), XXddb1_2.flatten())
        Theta = Theta.at[0:N_domain, 2 * N_domain :].set(
            jnp.reshape(val, (N_domain, N_domain + N_boundary))
        )
        Theta = Theta.at[2 * N_domain :, 0:N_domain].set(
            jnp.transpose(jnp.reshape(val, (N_domain, N_domain + N_boundary)))
        )

        val = vmap(
            lambda x1, x2, y1, y2: K.D_x2_kappa(x1, x2, y1, y2, kernel_parameter)
        )(XXddb0.flatten(), XXddb1.flatten(), XXddb0_2.flatten(), XXddb1_2.flatten())
        Theta = Theta.at[N_domain : 2 * N_domain, 2 * N_domain :].set(
            jnp.reshape(val, (N_domain, N_domain + N_boundary))
        )
        Theta = Theta.at[2 * N_domain :, N_domain : 2 * N_domain].set(
            jnp.transpose(onp.reshape(val, (N_domain, N_domain + N_boundary)))
        )
        return Theta


def construct_Theta_test(
    X_test,
    X_domain,
    X_boundary,
    eqn="Nonlinear_elliptic",
    kernel="Gaussian",
    kernel_parameter=0.2,
    nu=0.02,
):
    N_test = X_test.shape[0]
    N_domain = X_domain.shape[0]
    N_boundary = X_boundary.shape[0]

    # auxiliary variables to make things readable
    # X_test coordinates
    Xt0 = X_test[:, 0]
    Xt1 = X_test[:, 1]

    # interior points coordinates
    Xd0 = X_domain[:N_domain, 0]
    Xd1 = X_domain[:N_domain, 1]

    # interior + boundary points coordinates
    Xdb0 = jnp.concatenate([Xd0, X_boundary[:N_boundary, 0]])
    Xdb1 = jnp.concatenate([Xd1, X_boundary[:N_boundary, 1]])

    # test v.s. interior
    XXtd0 = jnp.transpose(jnp.tile(Xt0, (N_domain, 1)))
    XXtd1 = jnp.transpose(jnp.tile(Xt1, (N_domain, 1)))
    XXtd0_2 = jnp.tile(Xd0, (N_test, 1))
    XXtd1_2 = jnp.tile(Xd1, (N_test, 1))

    # test v.s. interior + boundary
    XXtdb0 = jnp.transpose(jnp.tile(Xt0, (N_domain + N_boundary, 1)))
    XXtdb1 = jnp.transpose(jnp.tile(Xt1, (N_domain + N_boundary, 1)))
    XXtdb0_2 = jnp.tile(Xdb0, (N_test, 1))
    XXtdb1_2 = jnp.tile(Xdb1, (N_test, 1))

    if kernel == "Gaussian":
        K = Gaussian_kernel()
    elif kernel == "anisotropic_Gaussian":
        K = Anisotropic_Gaussian_kernel()

    # constructing Theta matrix
    if eqn == "Nonlinear_elliptic":
        Theta_test = onp.zeros((N_test, 2 * N_domain + N_boundary))
        val = vmap(
            lambda x1, x2, y1, y2: K.Delta_y_kappa(x1, x2, y1, y2, kernel_parameter)
        )(XXtd0.flatten(), XXtd1.flatten(), XXtd0_2.flatten(), XXtd1_2.flatten())
        Theta_test[:, :N_domain] = onp.reshape(val, (N_test, N_domain))

        val = vmap(lambda x1, x2, y1, y2: K.kappa(x1, x2, y1, y2, kernel_parameter))(
            XXtdb0.flatten(), XXtdb1.flatten(), XXtdb0_2.flatten(), XXtdb1_2.flatten()
        )
        Theta_test[:, N_domain:] = onp.reshape(val, (N_test, N_domain + N_boundary))
        return Theta_test
    elif eqn == "Burgers":
        Theta_test = onp.zeros((N_test, 3 * N_domain + N_boundary))
        # constructing Theta matrix
        val = vmap(
            lambda x1, x2, y1, y2: K.D_y1_kappa(x1, x2, y1, y2, kernel_parameter)
            - nu * K.DD_y2_kappa(x1, x2, y1, y2, kernel_parameter)
        )(XXtd0.flatten(), XXtd1.flatten(), XXtd0_2.flatten(), XXtd1_2.flatten())
        Theta_test[:, :N_domain] = onp.reshape(val, (N_test, N_domain))

        val = vmap(
            lambda x1, x2, y1, y2: K.D_y2_kappa(x1, x2, y1, y2, kernel_parameter)
        )(XXtd0.flatten(), XXtd1.flatten(), XXtd0_2.flatten(), XXtd1_2.flatten())
        Theta_test[:, N_domain : 2 * N_domain] = onp.reshape(val, (N_test, N_domain))

        val = vmap(lambda x1, x2, y1, y2: K.kappa(x1, x2, y1, y2, kernel_parameter))(
            XXtdb0.flatten(), XXtdb1.flatten(), XXtdb0_2.flatten(), XXtdb1_2.flatten()
        )
        Theta_test[:, 2 * N_domain : 3 * N_domain + N_boundary] = onp.reshape(
            val, (N_test, N_domain + N_boundary)
        )
        return Theta_test
