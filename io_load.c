/*
 * io_load: Performs I/O in alternating threads.
 *
 * Copyright 2011 Google Inc.
 *
 *   Licensed under the Apache License, Version 2.0 (the "License");
 *   you may not use this file except in compliance with the License.
 *   You may obtain a copy of the License at
 *
 *       http://www.apache.org/licenses/LICENSE-2.0
 *
 *   Unless required by applicable law or agreed to in writing, software
 *   distributed under the License is distributed on an "AS IS" BASIS,
 *   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *   See the License for the specific language governing permissions and
 *   limitations under the License.
 */

#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <time.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <pthread.h>

#define NUM_THR 2

static char buffer[128 * 1024] __attribute__((aligned(512))) ;
const int ios_per_time = 1;
//const int ios_per_time = 1024;

struct io_params {
	int rw;
	int fd;
	int num_threads;
	pthread_cond_t io_cond;
	pthread_mutex_t io_mutex;
	int delay_ms;
};

/* Starting condition variable. */
static pthread_cond_t start_condition = PTHREAD_COND_INITIALIZER;

/* result = t2 - t1 */
static void diff_timespec(struct timespec *t1, struct timespec *t2,
                          struct timespec *result)
{
	*result = *t2;
	if (t1->tv_nsec > t2->tv_nsec) {
		result->tv_nsec += 1000000000UL;
		result->tv_sec -= 1;
	}
	result->tv_nsec -= t1->tv_nsec;
	result->tv_sec -= t1->tv_sec;
}

void *do_io(void *arg)
{
	struct io_params *params = arg;
	struct timespec t1, t2, t3;
	int fd = params->fd;
	int rw = params->rw;

	pthread_mutex_lock(&params->io_mutex);
	params->num_threads++;

	while (1) {
		int count = 0;
		pthread_cond_wait(&params->io_cond, &params->io_mutex);
		lseek(fd, 0, SEEK_SET);
		clock_gettime(CLOCK_MONOTONIC, &t1);
		while (count < ios_per_time) {
			ssize_t ret;
			switch (rw) {
			case 'r':
				ret = read(fd, buffer, sizeof(buffer));
				if (ret < 0) {
					perror("pread() fail");
					pthread_exit(NULL);
				}
				break;
			case 'w':
				ret = write(fd, buffer, sizeof(buffer));
				if (ret < 0) {
					perror("pwrite() fail");
					pthread_exit(NULL);
				}
				break;
			default:
				fprintf(stdout, "Illegal param: %c\n", rw);
				pthread_exit(NULL);
			}
			count++;
			if (params->delay_ms != 0)
				usleep(params->delay_ms * 1000);
		}
		clock_gettime(CLOCK_MONOTONIC, &t2);
		diff_timespec(&t1, &t2, &t3);
		{
		int io_size = (ios_per_time * sizeof(buffer))/(1024 * 1024);
		long long usec = t3.tv_sec * 1000000LL + t3.tv_nsec / 1000;
		fprintf(stdout, "IO'd %d MiB in %ld usec\n", io_size, usec);
		}
		pthread_cond_signal(&params->io_cond);
	}
}

static void start_thread(pthread_t *thr, struct io_params *params)
{
	int ret = pthread_create(thr, NULL, do_io, params);
	if (ret != 0) {
		perror("Could not create thread\n");
		exit(1);
	}
}

int main(int argc, char *argv[])
{
	int fd;
	struct io_params params;
	pthread_t thr[NUM_THR];
	void *return_value;

	int c;
	params.delay_ms = 0;

	while ((c = getopt(argc, argv, "d:")) != -1) {
		if (c == 'd') {
			params.delay_ms = atoi(optarg);
		}
	}

	if ((argc != 3) && (argc != 5)) {
		fprintf(stderr, "usage: %s [-d delayms] <r|w> <file>\n",
		        argv[0]);
		exit(1);
	}

	fd = open(argv[optind + 1], O_RDWR | O_DIRECT, S_IRUSR | S_IWUSR);
	if (fd < 0) {
		perror("Failure opening file.");
		exit(1);
	}
	params.rw = argv[optind][0];
	params.fd = fd;
	params.num_threads = 0;
	pthread_cond_init(&params.io_cond, NULL);
	pthread_mutex_init(&params.io_mutex, NULL);
	start_thread(&thr[0], &params);
	start_thread(&thr[1], &params);
	while (*(volatile int *)&params.num_threads != NUM_THR)
		sleep(1);
	pthread_cond_signal(&params.io_cond);
	pthread_join(thr[0], &return_value);
	pthread_join(thr[1], &return_value);
}
