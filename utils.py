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


import glob, logging, math, os, re, subprocess
import error

# Returns total memory in kb
def read_from_meminfo(key):
    meminfo = system_output('grep %s /proc/meminfo' % key)
    return int(re.search(r'\d+', meminfo).group(0))


def memtotal():
    return read_from_meminfo('MemTotal')


def get_device_id(device):
    """Returns a string consisting of the major:minor number of the device.

    Args:
        device: the name of the device

    Returns:
        a string consisting of the major:minor number of the device.
    """
    try:
        device_num = os.stat('/dev/%s' % device)
    except OSError:
        raise ValueError('/dev/%s is not a valid device.' % device)

    return '%s:%s' % (os.major(device_num.st_rdev),
                      os.minor(device_num.st_rdev))


def rounded_memtotal():
    # Get total of all physical mem, in kbytes
    usable_kbytes = memtotal()
    # usable_kbytes is system's usable DRAM in kbytes,
    #   as reported by memtotal() from device /proc/meminfo memtotal
    #   after Linux deducts 1.5% to 5.1% for system table overhead
    # Undo the unknown actual deduction by rounding up
    #   to next small multiple of a big power-of-two
    #   eg  12GB - 5.1% gets rounded back up to 12GB
    mindeduct = 0.015  # 1.5 percent
    maxdeduct = 0.055  # 5.5 percent
    # deduction range 1.5% .. 5.5% supports physical mem sizes
    #    6GB .. 12GB in steps of .5GB
    #   12GB .. 24GB in steps of 1 GB
    #   24GB .. 48GB in steps of 2 GB ...
    # Finer granularity in physical mem sizes would require
    #   tighter spread between min and max possible deductions

    # increase mem size by at least min deduction, without rounding
    min_kbytes   = int(usable_kbytes / (1.0 - mindeduct))
    # increase mem size further by 2**n rounding, by 0..roundKb or more
    round_kbytes = int(usable_kbytes / (1.0 - maxdeduct)) - min_kbytes
    # find least binary roundup 2**n that covers worst-cast roundKb
    mod2n = 1 << int(math.ceil(math.log(round_kbytes, 2)))
    # have round_kbytes <= mod2n < round_kbytes*2
    # round min_kbytes up to next multiple of mod2n
    phys_kbytes = min_kbytes + mod2n - 1
    phys_kbytes = phys_kbytes - (phys_kbytes % mod2n)  # clear low bits
    return phys_kbytes


def human_format(number):
    """Convert number to kilo / mega / giga format."""
    if number < 1024:
        return "%d" % number
    kilo = float(number) / 1024.0
    if kilo < 1024:
        return "%.2fk" % kilo
    meg = kilo / 1024.0
    if meg < 1024:
        return "%.2fM" % meg
    gig = meg / 1024.0
    return "%.2fG" % gig


def drop_caches():
    """Writes back all dirty pages to disk and clears all the caches."""
    system("sync")
    system("echo 3 > /proc/sys/vm/drop_caches")


def read_one_line(filename):
    """Open a file and read one line"""
    return open(filename, 'r').readline().rstrip('\n')


def write_one_line(filename, line):
    """Open a file and write one line, adding a newline at the end."""
    line = line.rstrip('\n') + '\n'
    logging.info('Writing in file:%s, line:%s' % (filename, line))
    f = open(filename, 'w')
    try:
        f.write(line)
    finally:
        f.close()


def system_output(command, ignore_status=False):
    """Run a shell command, return its stdout and stderr output.  """
    logging.debug("Running '%s'" % command)
    sp = subprocess.Popen(command, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          shell=True, executable="/bin/bash")
    result = ""
    try:
        exit_status = sp.wait()
        result = sp.stdout.read()
    finally:
        # close our ends of the pipes to the sp no matter what
        sp.stdout.close()
    if exit_status and not ignore_status:
        raise error.Error("Command '%s' returned non-zero exit status %d",
                          command, exit_status)
    if result and result[-1] == "\n":  result = result[:-1]
    return result


def system(command, ignore_status=False):
    """Run a command. """
    out = system_output(command, ignore_status)
    if out:
        logging.debug(out)


def pid_is_alive(pid):
    """
    True if process pid exists and is not yet stuck in Zombie state.
    Zombies are impossible to move between cgroups, etc.
    pid can be integer, or text of integer.
    """
    path = '/proc/%s/stat' % pid

    try:
        stat = read_one_line(path)
    except IOError:
        if not os.path.exists(path):
            # file went away
            return False
        raise

    return stat.split()[2] != 'Z'


def numa_nodes():
     """Return the ids of all the NUMA nodes in the system."""
     node_paths = glob.glob('/sys/devices/system/node/node*')
     nodes = [int(re.sub(r'.*node(\d+)', r'\1', x)) for x in node_paths]
     return (sorted(nodes))
