#include <mpi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    MPI_Init(&argc, &argv);
    int rank, size, length;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    char hostname[MPI_MAX_PROCESSOR_NAME] = {0};
    MPI_Get_processor_name(hostname, &length);
    int value = rank + 1;
    int sum = 0;
    MPI_Allreduce(&value, &sum, 1, MPI_INT, MPI_SUM, MPI_COMM_WORLD);
    char hosts[2][MPI_MAX_PROCESSOR_NAME] = {{0}};
    int valid = size == 2;
    if (valid) {
        MPI_Allgather(hostname, MPI_MAX_PROCESSOR_NAME, MPI_CHAR,
                      hosts, MPI_MAX_PROCESSOR_NAME, MPI_CHAR, MPI_COMM_WORLD);
        valid = sum == 3 && strcmp(hosts[0], hosts[1]) != 0;
    }
    printf("{\"rank\":%d,\"size\":%d,\"hostname\":\"%s\",\"sum\":%d,\"valid\":%s}\n",
           rank, size, hostname, sum, valid ? "true" : "false");
    fflush(stdout);
    MPI_Finalize();
    return valid ? EXIT_SUCCESS : EXIT_FAILURE;
}
