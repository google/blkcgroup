# Copyright 2011 Google Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# Utility functions for managing tracing.

import errno, fcntl, logging, os, threading, time

class simple_tracer(threading.Thread):
    def __init__(self, output_file):
        self.outfile = output_file
        self.trace_running = False
        threading.Thread.__init__(self)


    def writeline(self, filename, value, mode):
        """ Write a single line to a file & close.
        """
        fd = open(filename, mode)
        fd.write(value)
        fd.close()


    def setup_tracepoints(self, tracepoints):
        """Set up the specified trace points.
        """
        interface = "/sys/kernel/debug/tracing/set_event"
        try:
            self.writeline(interface, "", 'w')
            for tp in tracepoints:
                logging.debug("Setting up tracepoint %s", tp)
                self.writeline(interface, tp, 'a')
        except IOError:
            logging.error("Failed to set up tracepoints.")
            return False
        return True


    def toggle_tracing(self, value):
        """Toggle the value of the kernel tracing interface.
        """
        try:
            logging.debug("Setting tracing_enabled to %s", value)
            self.writeline("/sys/kernel/debug/tracing/tracing_enabled",
                           value, 'w')
            logging.debug("Setting tracing_on to %s", value)
            self.writeline("/sys/kernel/debug/tracing/tracing_on",
                           value, 'w')
        except IOError:
            logging.error("Failed to set tracing to %s.", value)
            return False
        return True


    def enable_tracing(self):
        """Enable tracing via the kernel interfaces.
        """
        return self.toggle_tracing("1")


    def disable_tracing(self):
        """Disable tracing via the kernel interaces.
        """
        return self.toggle_tracing("0")


    def start_tracing(self):
        """Start tracing and stream the output to a file.
        """
        if not self.enable_tracing():
            return False
        trace_buffer = "/sys/kernel/debug/tracing/trace_pipe"
        try:
            logging.debug("Opening trace buffer.")
            self.trace_buffer_fd = open(trace_buffer, 'r')

            logging.debug("Making trace buffer reads non-blocking.")
            flags = fcntl.fcntl(self.trace_buffer_fd, fcntl.F_GETFL)
            flags |= os.O_NONBLOCK
            fcntl.fcntl(self.trace_buffer_fd, fcntl.F_SETFL, flags)

            logging.debug("Opening output file.")
            self.outfile_fd = open(self.outfile, 'w', 0)
            self.trace_running = True
            self.start()
        except IOError, RuntimeError:
            logging.error("Failed to start tracing")
            self.disable_tracing()
            return False
        return True


    def stop_tracing(self):
        """Stop tracing if it is running.
        """
        if self.trace_running:
            self.trace_running = False
            try:
                logging.debug("Stopping tracing.")
                self.join()
            except RuntimeError:
                logging.error("Failed to join on tracing thread.");

            try:
                self.trace_buffer_fd.close()
                self.outfile_fd.close()
            except IOError:
                logging.error("Failed to close trace file handles.");

            self.disable_tracing()
            logging.debug("Tracing stopped.")


    def run(self):
        """Loops around dumping the trace buffer to the output file until
           stop_tracing() is called.
        """
        logging.debug("Tracing thread started.")
        while self.trace_running:
            try:
                line = self.trace_buffer_fd.readline()
                self.outfile_fd.write(line)
            except IOError, e:
                if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                    time.sleep(1)
                else:
                    logging.error("Tracing thread got error %s", strerr)
                    break
        logging.debug("Tracing thread terminated.")
