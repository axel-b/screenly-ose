#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>
#include <errno.h>
#include <math.h>



//       int fstat(int fd, struct stat *buf);

char * watchfile = "/tmp/screenly.watchdog";
char * repaircommand = "/home/pi/screenly/testrepair/repaircommand";
int mx = 15 * 60;
int slack = 5 * 60;

void main(int argc, char **argv)
{
	int fd;
	struct stat st;
	char buf[1024];
	float cvt;
	time_t duration;
	time_t deadline;
	time_t mtime;
	time_t curtime;
	time_t remaining;
	time_t diff;
	int n;
	int ret;
	int status;

	if(argc == 2 && strcmp(argv[1], "test") == 0) {
		fprintf(stdout, "testing\n");
		fd = open(watchfile, O_RDONLY);
		if (fd < 0) { 
			int errsv = errno;
			fprintf(stdout, "error open-ing %s: %s\n", watchfile, strerror(errsv));
			exit(1);
		}
		if (fstat(fd, &st) < 0) {
			int errsv = errno;
			fprintf(stdout, "error stat-ing %s: %s\n", watchfile, strerror(errsv));
			exit(2);
		}
		mtime = st.st_mtime;
		n = read(fd, &buf, sizeof(buf));
		if (n < 0) {
			int errsv = errno;
			fprintf(stdout, "error read-ing %s: %s\n", watchfile, strerror(errsv));
			exit(3);
		}
		close(fd);
		cvt = atof(buf);
		if (cvt >= 0)
			duration = (int)ceil(cvt);
		else
			duration = (int)mx;
		deadline = mtime + duration;
		curtime = time(0);
		remaining = deadline - curtime;
		diff = slack + remaining;
		fprintf(stdout, "read: %f, duration: %d, mtime: %d, deadline: %d, curtime: %d, remaining: %d, diff: %d\n", cvt, duration, mtime, deadline, curtime, remaining, diff);
		if (diff >= 0) {
			exit(0);
		}
		fprintf(stdout, "error diff negative: %d\n", diff);
		exit(4);
	} else if (argc == 3 && strcmp(argv[1], "repair") == 0) {
		fprintf(stdout, "repairing\n");
		ret = system(repaircommand);
		if (ret < 0) {
			int errsv = errno;
			fprintf(stdout, "error starting repaircommand %s: %s\n", repaircommand, strerror(errsv));
			exit(5);
		}
		status = WEXITSTATUS(ret);
		if (status != 0) {
			fprintf(stdout, "error running repaircommand %s: %d\n", repaircommand, status);
		}
		exit(status);
	} else {
		fprintf(stdout, "usage: testrepair test\n");
		fprintf(stdout, "usage: testrepair repair <code>\n");
		exit(6);
	}
}
