#!/usr/bin/env python
# minimap2 0.0.1
# Generated by dx-app-wizard.
#
# Basic execution pattern: Your app will run on a single machine from
# beginning to end.
#
# See https://wiki.dnanexus.com/Developer-Portal for documentation and
# tutorials on how to modify this file.
#
# DNAnexus Python Bindings (dxpy) documentation:
#   http://autodoc.dnanexus.com/bindings/python/current/
from __future__ import print_function
import os
import subprocess
import re
import multiprocessing

import dx_utils
import dxpy


BAMSORMADUP_LIB_DIR = '/usr/local/lib/'


def _get_mem_in_gb(frac=0.8):
    with open('/proc/meminfo') as fh:
        memory = fh.readline().strip().split()[1]

    return int(float(memory)*frac) >> 20


def _get_output_prefix(fn):
    prefix = os.path.splitext(re.sub('.gz$', '', fn))[0]
    search_match = re.search('_R[12]', prefix)
    if search_match is not None:
        prefix = prefix[0:search_match.start()]

    return prefix


def _list2cmdlines_pipe(*cmds):
    cmdline = ''
    for cmd in cmds:
        cmdline += subprocess.list2cmdline(cmd) + ' | '

    return cmdline.rstrip(' | ')


@dxpy.entry_point('main')
def main(reads_fastqgz, genome_fastagz, sequencing_technology='pacbio', reads2_fastqgz=None):
    os.environ['LD_LIBRARY_PATH'] = (os.environ.get('LD_LIBRARY_PATH', '') + 
        ':{0}'.format(BAMSORMADUP_LIB_DIR)).lstrip(':')
    # Create named pipes for the input reads and download the reference genome.
    reads_fastqgz = dx_utils.download_and_gunzip_file(reads_fastqgz, skip_decompress=True, create_named_pipe=True)
    output_prefix = _get_output_prefix(reads_fastqgz)
    if reads2_fastqgz is not None:
        reads2_fastqgz = dx_utils.download_and_gunzip_file(reads2_fastqgz, skip_decompress=True, create_named_pipe=True)
    genome_fastagz = dx_utils.download_and_gunzip_file(genome_fastagz)

    # Make fifo for output bam and attach upload process
    os.mkfifo('{0}.bam'.format(output_prefix))
    upload_proc = subprocess.Popen(['dx', 'upload', '--brief', '{0}.bam'.format(output_prefix)], stdout=subprocess.PIPE)

    # Call minimap
    minimap2_cmd = ['minimap2', '-ax']
    if sequencing_technology == 'pacbio':
        minimap2_cmd += ['map-pb', '-L']
    elif sequencing_technology == 'ont':
        minimap2_cmd += ['map-ont', '-L']
    else:
        minimap2_cmd += ['sr']

    minimap2_cmd += [genome_fastagz, reads_fastqgz]
    if reads2_fastqgz is not None:
        minimap2_cmd += [reads2_fastqgz]

    # Pipe on bamsormadup or sambamba
    if sequencing_technology == 'illumina':
        bamsormadup_cmd = ['bamsormadup', 'SO=coordinate', 'threads={0}'.format(multiprocessing.cpu_count()), 
            'inputformat=sam', 'indexfilename="{0}".bam.bai'.format(output_prefix)]
        print(_list2cmdlines_pipe(minimap2_cmd, bamsormadup_cmd))
        # Now actually make the calls
        minimap_proc = subprocess.Popen(minimap2_cmd, stdout=subprocess.PIPE)
        with open('{0}.bam'.format(output_prefix), 'w') as fh:
            subprocess.check_call(bamsormadup_cmd, stdin=minimap_proc.stdout, stdout=fh)
    else:
        view_cmd = ['sambamba', 'view', '--sam-input', '--format=bam', '--compression-level=0', '/dev/stdin']
        sort_cmd = ['sambamba', 'sort', '-m', '{0}G'.format(_get_mem_in_gb()), '-o', 
            '{0}.bam'.format(output_prefix), '-t', str(multiprocessing.cpu_count()), '/dev/stdin']
        print(_list2cmdlines_pipe(minimap2_cmd, view_cmd, sort_cmd))
        # Now actually make the calls
        minimap_proc = subprocess.Popen(minimap2_cmd, stdout=subprocess.PIPE)
        sambamba_view_proc = subprocess.Popen(view_cmd, stdin=minimap_proc.stdout, stdout=subprocess.PIPE)
        subprocess.check_call(sort_cmd, stdin=sambamba_view_proc.stdout)

    minimap_proc.communicate()
    bam_fid, err = upload_proc.communicate()
    # Now upload the output
    output = {}
    #output['mapped_reads'] = dxpy.dxlink(dxpy.upload_local_file('{0}.bam'.format(output_prefix)))
    output['mapped_reads'] = dxpy.dxlink(bam_fid.strip())

    return output

dxpy.run()