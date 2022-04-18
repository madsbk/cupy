import sys
import time

import cupy
from cupy import cuda
from cupy.cuda import nccl
from cupy import testing

from cupyx.distributed import init_process_group
from cupyx.distributed._nccl_comm import NCCLBackend
from cupyx.distributed._store import ExceptionAwareProcess

nccl_available = nccl.available


N_WORKERS = 2


def _launch_workers(func, args=(), n_workers=N_WORKERS):
    processes = []
    # TODO catch exceptions
    for rank in range(n_workers):
        p = ExceptionAwareProcess(
            target=func,
            args=(rank,) + args)
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


def broadcast(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_broadcast(rank, root, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(N_WORKERS, rank, force_store=force_store)
        expected = cupy.arange(2 * 3 * 4, dtype=dtype).reshape((2, 3, 4))
        if rank == root:
            in_array = expected
        else:
            in_array = cupy.zeros((2, 3, 4), dtype=dtype)
        comm.broadcast(in_array, root)
        testing.assert_allclose(in_array, expected)

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_broadcast(MPI.COMM_WORLD.Get_rank(), 0, dtype, False)
        run_broadcast(MPI.COMM_WORLD.Get_rank(), 1, dtype, False)
    else:
        _launch_workers(run_broadcast, (0, dtype))
        _launch_workers(run_broadcast, (1, dtype))


def reduce(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_reduce(rank, root, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(N_WORKERS, rank, force_store=force_store)
        in_array = cupy.arange(2 * 3 * 4, dtype='f').reshape(2, 3, 4)
        out_array = cupy.zeros((2, 3, 4), dtype='f')
        comm.reduce(in_array, out_array, root)
        if rank == root:
            testing.assert_allclose(out_array, 2 * in_array)

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_reduce(MPI.COMM_WORLD.Get_rank(), 0, dtype, False)
        run_reduce(MPI.COMM_WORLD.Get_rank(), 1, dtype, False)
    else:
        _launch_workers(run_reduce, (0, dtype))
        _launch_workers(run_reduce, (1, dtype))


def all_reduce(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_all_reduce(rank, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(N_WORKERS, rank, force_store=force_store)
        in_array = cupy.arange(2 * 3 * 4, dtype='f').reshape(2, 3, 4)
        out_array = cupy.zeros((2, 3, 4), dtype='f')

        comm.all_reduce(in_array, out_array)
        testing.assert_allclose(out_array, 2 * in_array)

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_all_reduce(MPI.COMM_WORLD.Get_rank(), dtype, False)
    else:
        _launch_workers(run_all_reduce, (dtype,))


def reduce_scatter(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_reduce_scatter(rank, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(rank, force_store=force_store)
        in_array = 1 + cupy.arange(
            N_WORKERS * 10, dtype='f').reshape(N_WORKERS, 10)
        out_array = cupy.zeros((10,), dtype='f')

        comm.reduce_scatter(in_array, out_array, 10)
        testing.assert_allclose(out_array, 2 * in_array[rank])

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_reduce_scatter(MPI.COMM_WORLD.Get_rank(), dtype, False)
    else:
        _launch_workers(run_reduce_scatter, (dtype,))


def all_gather(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_all_gather(rank, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(rank, force_store=force_store)
        in_array = (rank + 1) * cupy.arange(
            N_WORKERS * 10, dtype='f').reshape(N_WORKERS, 10)
        out_array = cupy.zeros((N_WORKERS, 10), dtype='f')
        comm.all_gather(in_array, out_array, 10)
        expected = 1 + cupy.arange(N_WORKERS).reshape(N_WORKERS, 1)
        expected = expected * cupy.broadcast_to(
            cupy.arange(10, dtype='f'), (N_WORKERS, 10))
        testing.assert_allclose(out_array, expected)

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_all_gather(MPI.COMM_WORLD.Get_rank(), dtype, False)
    else:
        _launch_workers(run_all_gather, (dtype,))


def send_and_recv(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_send_and_recv(rank, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(N_WORKERS, rank, force_store=force_store)
        in_array = cupy.arange(10, dtype='f')
        out_array = cupy.zeros((10,), dtype='f')
        if rank == 0:
            comm.send(in_array, 1)
        else:
            comm.recv(out_array, 0)
            testing.assert_allclose(out_array, in_array)

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_send_and_recv(MPI.COMM_WORLD.Get_rank(), dtype, False)
    else:
        _launch_workers(run_send_and_recv, (dtype,))


def send_recv(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_send_recv(rank, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(N_WORKERS, rank, force_store=force_store)
        in_array = cupy.arange(10, dtype='f')
        for i in range(N_WORKERS):
            out_array = cupy.zeros((10,), dtype='f')
            comm.send_recv(in_array, out_array, i)
            testing.assert_allclose(out_array, in_array)

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_send_recv(MPI.COMM_WORLD.Get_rank(), dtype, False)
    else:
        _launch_workers(run_send_recv, (dtype,))


def scatter(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_scatter(rank, root, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(N_WORKERS, rank, force_store=force_store)
        in_array = 1 + cupy.arange(
            N_WORKERS * 10, dtype='f').reshape(N_WORKERS, 10)
        out_array = cupy.zeros((10,), dtype='f')

        comm.scatter(in_array, out_array, root)
        if rank > 0:
            testing.assert_allclose(out_array, in_array[rank])

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_scatter(MPI.COMM_WORLD.Get_rank(), 0, dtype, False)
        run_scatter(MPI.COMM_WORLD.Get_rank(), 1, dtype, False)
    else:
        _launch_workers(run_scatter, (0, dtype))
        _launch_workers(run_scatter, (1, dtype))


def gather(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_gather(rank, root, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(N_WORKERS, rank, force_store=force_store)
        in_array = (rank + 1) * cupy.arange(10, dtype='f')
        out_array = cupy.zeros((N_WORKERS, 10), dtype='f')
        comm.gather(in_array, out_array, root)
        if rank == root:
            expected = 1 + cupy.arange(N_WORKERS).reshape(N_WORKERS, 1)
            expected = expected * cupy.broadcast_to(
                cupy.arange(10, dtype='f'), (N_WORKERS, 10))
            testing.assert_allclose(out_array, expected)

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_gather(MPI.COMM_WORLD.Get_rank(), 0, dtype, False)
        run_gather(MPI.COMM_WORLD.Get_rank(), 1, dtype, False)
    else:
        _launch_workers(run_gather, (0, dtype))
        _launch_workers(run_gather, (1, dtype))


def all_to_all(dtype, use_mpi=False):
    if dtype in 'hH':
        return  # nccl does not support int16

    def run_all_to_all(rank, dtype, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(N_WORKERS, rank, force_store=force_store)
        in_array = cupy.arange(
            N_WORKERS * 10, dtype='f').reshape(N_WORKERS, 10)
        out_array = cupy.zeros((N_WORKERS, 10), dtype='f')
        comm.all_to_all(in_array, out_array)
        expected = (10 * rank) + cupy.broadcast_to(
            cupy.arange(10, dtype='f'), (N_WORKERS, 10))
        testing.assert_allclose(out_array, expected)

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_all_to_all(MPI.COMM_WORLD.Get_rank(), dtype, False)
    else:
        _launch_workers(run_all_to_all, (dtype,))


def barrier(use_mpi=False):
    def run_barrier(rank, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = NCCLBackend(N_WORKERS, rank, force_store=force_store)
        comm.barrier()
        before = time.time()
        if rank == 0:
            time.sleep(2)
        comm.barrier()
        after = time.time()
        assert int(after - before) == 2

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_barrier(MPI.COMM_WORLD.Get_rank(), False)
    else:
        _launch_workers(run_barrier)


def init(use_mpi=False):
    def run_init(rank, force_store=True):
        dev = cuda.Device(rank)
        dev.use()
        comm = init_process_group(N_WORKERS, rank, force_store=force_store)
        # Do a simple call to verify we got a valid comm
        in_array = cupy.zeros(1)
        if rank == 0:
            in_array = in_array + 1
        comm.broadcast(in_array, 0)
        testing.assert_allclose(in_array, cupy.ones(1))

    if use_mpi:
        from mpi4py import MPI
        # This process was run with mpiexec
        run_init(MPI.COMM_WORLD.Get_rank(), dtype, False)
        run_init(MPI.COMM_WORLD.Get_rank(), dtype, False)
    else:
        _launch_workers(run_init)


if __name__ == '__main__':
    # Run the templatized test
    func = globals()[sys.argv[1]]
    # dtype is the char representation
    use_mpi = True if sys.argv[2] == "mpi" else False
    dtype = sys.argv[3] if len(sys.argv) == 4 else None
    if dtype is not None:
        func(dtype, use_mpi)
    else:
        func(use_mpi)
