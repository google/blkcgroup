/*
 * rand_read: Performs reads of at random offsets in the given file.
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

#define _LARGEFILE64_SOURCE

#include <sys/types.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include <float.h>
#include <signal.h>

const char *program;

sig_atomic_t killed;

void usage()
{
	fprintf(stderr,
		"Usage: %s [ -d DELAYMS ] [ -c COUNT ] <log2(IO size)> "
		"<filename>\n",
		program);
}

void signal_handler(int signal) {
	killed = 1;
}

/*
 * Performs a series of random reads in a file.
 *
 * Randomly reads from FILENAME, COUNT times. Sleeps for SLEEP_TIME between
 * reads. ioSizeBits contols the size of the individual reads.
 */
static int random_read(char *filename, off64_t count,
		       const struct timespec sleep_time,
		       int ioSizeBits)
{
	char *buffer;
	int fd;
	struct stat64 statBuf;
	off64_t i, offset, ret, size;
	struct timespec time_remaining;
	double latency, min_lat, max_lat, mean, n_variance, prev_mean;
	struct timeval start_time, finish_time, elapsed_time;

	buffer = malloc((1 << ioSizeBits) * sizeof(char));
	if (buffer == NULL) {
		fprintf(stderr, "Malloc failed\n");
		return -1;
	}

	fd = open(filename, O_RDONLY | O_LARGEFILE);
	if (fd < 0) {
		fprintf(stderr, "Failed to open file %s: %s\n", filename,
			strerror(errno));
		return -1;
	}

	ret = fstat64(fd, &statBuf);
	if (ret < 0) {
		fprintf(stderr, "Stat failed: %s\n", strerror(errno));
		return -1;
	}
	size = statBuf.st_size >> ioSizeBits;
	if (count == 0) {
		/*
		 * The default count reads <= 10% of the file's data to
		 * minimize cache hits.
		 * This default count is capped to 10,000 to limit the maximum
		 * test time
		 * to about 8 minutes (assuming 20msec per seek).
		 */
		count = size / 10U;
		count = (count > 10000U) ? 10000U : count;
	}
	printf("Doing %zd random reads\n", count);

	min_lat = DBL_MAX;
	max_lat = 0.0;
	mean = n_variance = 0.0;

	for (i = 0; i < count && !killed; ++i) {
		offset = (((off64_t) rand()) % size) << ioSizeBits;

		ret = lseek64(fd, offset, SEEK_SET);
		if (ret < 0) {
			fprintf(stderr, "seek failed: %s\n", strerror(errno));
			return -1;
		}

		gettimeofday(&start_time, NULL);
		ret = read(fd, buffer, (1 << ioSizeBits));
		if (ret < 0) {
			fprintf(stderr, "read failed: %s\n", strerror(errno));
			return -1;
		}
		gettimeofday(&finish_time, NULL);

		if (sleep_time.tv_sec != -1) {
			time_remaining = sleep_time;
			do {
				ret =
				    nanosleep(&time_remaining, &time_remaining);
			} while (ret == EINTR);
		}

		/*
		 * compute latancy statistics, currently min, max, mean and std
		 * dev.
		 */
		timersub(&finish_time, &start_time, &elapsed_time);
		latency = elapsed_time.tv_sec + 1e-6*elapsed_time.tv_usec;
		min_lat = fminl(min_lat, latency);
		max_lat = fmaxl(max_lat, latency);

		if (i == 0)
			mean = latency;
		prev_mean = mean;
		mean += (latency - mean) / (i + 1);
		n_variance += (latency - prev_mean) * (latency - mean);
	}
	close(fd);

	if (killed)
		fprintf(stderr, "Interrupted\n");

	printf("min_read_latency %.2f ms\n"
	       "max_read_latency %.2f ms\n"
	       "mean_read_latency %.2f ms\n"
	       "stddev_read_latency %.2f ms\n"
	       "reads %ld count\n",
	       min_lat*1000, max_lat*1000, mean*1000,
	       sqrt(n_variance / i)*1000, i);

	return 0;
}

int main(int argc, char **argv)
{
	char *filename;
	int ioSizeBits;
	off64_t count;
	int sleep_ms;
	ldiv_t ldt;
	long sleep_ns;
	struct timespec sleep_time;
	int opt;
	struct sigaction sig_action;

	program = argv[0];

	sleep_ms = 0;
	count = 0;
	sleep_time.tv_sec = -1;

	while ((opt = getopt(argc, argv, "c:d:")) != -1) {
		switch (opt) {
		case 'c':
			count = atoi(optarg);
			if (count < 0) {
				usage();
				exit(1);
			}
			break;
		case 'd':
			sleep_ms = atoi(optarg);
			if (sleep_ms < 0) {
				usage();
				exit(1);
			}
			sleep_ns = 1000000L * sleep_ms;
			ldt = ldiv(sleep_ns, 1000000000L);
			sleep_time.tv_sec = ldt.quot;
			sleep_time.tv_nsec = ldt.rem;
			break;
		default:
			usage();
		}
	}

	if (argc != optind + 2) {
		usage();
		exit(1);
	}

	ioSizeBits = atoi(argv[optind]);
	if (ioSizeBits < 0) {
		usage();
		exit(1);
	}
	printf("Reading in %d byte chunks\n", 1 << ioSizeBits);

	filename = argv[optind + 1];

	srand(42);

	killed = 0;
	memset(&sig_action, 0, sizeof(sig_action));
	sig_action.sa_handler = signal_handler;
	sigaction(SIGINT, &sig_action, NULL);
	sigaction(SIGTERM, &sig_action, NULL);

	return random_read(filename, count, sleep_time, ioSizeBits);
}
