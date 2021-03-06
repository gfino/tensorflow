# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""RMSprop optimizer for Tensorflow.

rmsprop algorithm [tieleman2012rmsprop]

A detailed description of rmsprop.

- maintain a moving (discounted) average of the square of gradients
- divide gradient by the root of this average

mean_square = rho * mean_square{t-1} + (1-rho) * gradient ** 2
mom = momentum * mom{t-1} + learning_rate * g_t / sqrt(mean_square)
delta = - mom

This implementation of RMSProp uses plain momentum, not Nesterov momentum.

The centered version additionally maintains a moving (discounted) average of the
gradients, and uses that average to estimate the variance:

mean_grad = rho * mean_square{t-1} + (1-rho) * gradient
mean_square = rho * mean_square{t-1} + (1-rho) * gradient ** 2
mom = momentum * mom{t-1} + learning_rate * g_t /
    sqrt(mean_square - mean_grad**2)
delta = - mom
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tensorflow.python.keras.optimizer_v2 import optimizer_v2
from tensorflow.python.ops import array_ops

from tensorflow.python.training import training_ops


class RMSProp(optimizer_v2.OptimizerV2):
  """RMSProp optimizer.

  It is recommended to leave the parameters of this optimizer at their default
  values (except the learning rate, which can be freely tuned).

  This optimizer is usually a good choice for recurrent neural networks.

  Some of the args below are hyperparameters, where a hyperparameter is
  defined as a scalar Tensor, a regular Python value, or a callable (which
  will be evaluated when `apply_gradients` is called) returning a scalar
  Tensor or a Python value.

  Note that in the dense implementation of this algorithm, variables and their
  corresponding accumulators (momentum, gradient moving average, square
  gradient moving average) will be updated even if the gradient is zero
  (i.e. accumulators will decay, momentum will be applied). The sparse
  implementation (used when the gradient is an `IndexedSlices` object,
  typically because of `tf.gather` or an embedding lookup in the forward pass)
  will not update variable slices or their accumulators unless those slices
  were used in the forward pass (nor is there an "eventual" correction to
  account for these omitted updates). This leads to more efficient updates for
  large embedding lookup tables (where most of the slices are not accessed in
  a particular graph execution), but differs from the published algorithm.

  Arguments:
      learning_rate: A float hyperparameter >= 0. The learning rate.
      rho: A float hyperparameter >= 0. Discounting factor for the
        history/coming gradient.
      momentum: A float hyperparameter >= 0.
      epsilon: A float hyperparameter >= 0 . Small value to initialize the
        average square gradient variable and avoid zero denominator.
      centered: If True, gradients are normalized by the estimated variance of
        the gradient; if False, by the uncentered second moment. Setting this to
        True may help with training, but is slightly more expensive in terms of
        computation and memory. Defaults to False.
      name: Optional name prefix for the operations created when applying
        gradients. Defaults to "RMSProp".
  """

  def __init__(self,
               learning_rate=0.001,
               rho=0.9,
               momentum=None,
               epsilon=1e-10,
               centered=False,
               name="RMSProp"):
    super(RMSProp, self).__init__(name)
    # Momentum default is `None` for consistency with SGD
    # but underlying implementation uses `momentum` hyperparameter here
    # regardless unlike SGD. Since extneral Keras RMSProp does not have
    # a `momentum` weight, for compatibility with external Keras h5 files,
    # when  `momentum` was set as `None` we should ignore the `momentum`
    # variable in `get_weights` and not require it in `set_weights`.
    if momentum is None:
      momentum = 0.0
    self._set_hyper("learning_rate", learning_rate)
    self._set_hyper("rho", rho)
    self._set_hyper("momentum", momentum)
    self._set_hyper("epsilon", epsilon)

    self._centered = centered

  def _create_vars(self, var_list, state):
    for v in var_list:
      init_rms = state.get_hyper(
          "epsilon", v.dtype.base_dtype) * array_ops.ones_like(v)
      state.create_slot_with_initializer(v, init_rms, v.get_shape(),
                                         v.dtype.base_dtype, "rms")
      if self._centered:
        state.zeros_slot(v, "mg")
      state.zeros_slot(v, "momentum")

  def _apply_dense(self, grad, var, state):
    rms = state.get_slot(var, "rms")
    mom = state.get_slot(var, "momentum")
    if self._centered:
      mg = state.get_slot(var, "mg")
      return training_ops.apply_centered_rms_prop(
          var,
          mg,
          rms,
          mom,
          state.get_hyper("learning_rate", var.dtype.base_dtype),
          state.get_hyper("rho", var.dtype.base_dtype),
          state.get_hyper("momentum", var.dtype.base_dtype),
          # epsilon is now the rms initial value and is not added to the
          # denominator anymore, hence calling the kernel op with epsilon=0.
          0,
          grad,
          use_locking=self._use_locking).op
    else:
      return training_ops.apply_rms_prop(
          var,
          rms,
          mom,
          state.get_hyper("learning_rate", var.dtype.base_dtype),
          state.get_hyper("rho", var.dtype.base_dtype),
          state.get_hyper("momentum", var.dtype.base_dtype),
          0,
          grad,
          use_locking=self._use_locking).op

  def _resource_apply_dense(self, grad, var, state):
    rms = state.get_slot(var, "rms")
    mom = state.get_slot(var, "momentum")
    if self._centered:
      mg = state.get_slot(var, "mg")
      return training_ops.resource_apply_centered_rms_prop(
          var.handle,
          mg.handle,
          rms.handle,
          mom.handle,
          state.get_hyper("learning_rate", var.dtype.base_dtype),
          state.get_hyper("rho", var.dtype.base_dtype),
          state.get_hyper("momentum", var.dtype.base_dtype),
          0,
          grad,
          use_locking=self._use_locking)
    else:
      return training_ops.resource_apply_rms_prop(
          var.handle,
          rms.handle,
          mom.handle,
          state.get_hyper("learning_rate", var.dtype.base_dtype),
          state.get_hyper("rho", var.dtype.base_dtype),
          state.get_hyper("momentum", var.dtype.base_dtype),
          0,
          grad,
          use_locking=self._use_locking)

  def _apply_sparse(self, grad, var, state):
    rms = state.get_slot(var, "rms")
    mom = state.get_slot(var, "momentum")
    if self._centered:
      mg = state.get_slot(var, "mg")
      return training_ops.sparse_apply_centered_rms_prop(
          var,
          mg,
          rms,
          mom,
          state.get_hyper("learning_rate", var.dtype.base_dtype),
          state.get_hyper("rho", var.dtype.base_dtype),
          state.get_hyper("momentum", var.dtype.base_dtype),
          0,
          grad.values,
          grad.indices,
          use_locking=self._use_locking)
    else:
      return training_ops.sparse_apply_rms_prop(
          var,
          rms,
          mom,
          state.get_hyper("learning_rate", var.dtype.base_dtype),
          state.get_hyper("rho", var.dtype.base_dtype),
          state.get_hyper("momentum", var.dtype.base_dtype),
          0,
          grad.values,
          grad.indices,
          use_locking=self._use_locking)

  def _resource_apply_sparse(self, grad, var, indices, state):
    rms = state.get_slot(var, "rms")
    mom = state.get_slot(var, "momentum")
    if self._centered:
      mg = self.get_slot(var, "mg")
      return training_ops.resource_sparse_apply_centered_rms_prop(
          var.handle,
          mg.handle,
          rms.handle,
          mom.handle,
          state.get_hyper("learning_rate", var.dtype.base_dtype),
          state.get_hyper("rho", var.dtype.base_dtype),
          state.get_hyper("momentum", var.dtype.base_dtype),
          0,
          grad,
          indices,
          use_locking=self._use_locking)
    else:
      return training_ops.resource_sparse_apply_rms_prop(
          var.handle,
          rms.handle,
          mom.handle,
          state.get_hyper("learning_rate", var.dtype.base_dtype),
          state.get_hyper("rho", var.dtype.base_dtype),
          state.get_hyper("momentum", var.dtype.base_dtype),
          0,
          grad,
          indices,
          use_locking=self._use_locking)
