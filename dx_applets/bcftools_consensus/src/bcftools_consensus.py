#!/usr/bin/env python
# bcftools_merge 0.0.1
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

import os
import dxpy
import multiprocessing
import subprocess

import dx_utils

VCF_FOFN = 'input_vcfs.fofn'


def _list2cmdlines_pipe(*cmds):
    cmdline = ''
    for cmd in cmds:
        cmdline += subprocess.list2cmdline(cmd) + ' | '

    return cmdline.rstrip(' | ')

@dxpy.entry_point('main')
def main(**job_inputs):
    input_vcfs = [dx_utils.download_and_gunzip_file(f, skip_decompress=True) for f in job_inputs['input_vcfs']]
    input_ref = dx_utils.download_and_gunzip_file(job_inputs['ref_fasta'], skip_decompress=True)
    map(dx_utils.run_cmd, ['tabix {0}'.format(vcf) for vcf in input_vcfs])
    with open(VCF_FOFN, 'w') as fh:
        fh.write('\n'.join(input_vcfs))

    # get the bcftools version and help doc
    cmd = ['bcftools', '--help']
    dx_utils.run_cmd(cmd)

    output_prefix = job_inputs.get('output_prefix', '')
    output_bcf = output_prefix + 'concat' + '.bcf'
    # concatenate the bcf/vcf files
    concat_cmd = ['bcftools', 'concat', '-f', VCF_FOFN]
    view_cmd = ['bcftools', 'view', '-Ou', '-e', '\'type="ref"\'']
    norm_cmd = ['bcftools', 'norm', '-Ob', '-f', input_ref, '-o', 
                output_bcf, '--threads={0}'.format(multiprocessing.cpu_count())]
    # print the commands
    print(_list2cmdlines_pipe(concat_cmd, view_cmd, norm_cmd))
    
    # now run the commands
    concat_process = subprocess.Popen(concat_cmd, stdout=subprocess.PIPE)
    view_process = subprocess.Popen(view_cmd, stdin=concat_process.stdout,
                                    stdout=subprocess.PIPE)
    subprocess.check_call(norm_cmd, stdin=view_process.stdout)

    # call consensus
    output_fasta = output_prefix + 'consensus.fasta'
    consensus_filter = '\'QUAL>1 && (GT="AA" || GT="Aa")\''
    cmd = ['bcftools', 'consensus', '-i', consensus_filter, '-Hla', '-f', 
           input_ref, output_bcf, '>', output_fasta]
    dx_utils.run_cmd(cmd)

    # get statistics
    output_count = output_prefix + 'count.numvar'
    cmd = ['bcftools', 'view', '-H', '-i', consensus_filter, '-Ov', output_bcf,
           '|', 'awk', '-F', '\"\\t\" \'{print $4\"\\t\"$5}\'', '|', 'awk', 
           ("\'\{lenA=length($1); lenB=length($2); if (lenA < lenB )" 
           "{sum+=lenB-lenA} else if ( lenA > lenB ) { sum+=lenA-lenB } else "
           "{sum+=lenA}} END {print sum}\'"),
            '>', output_count]
    dx_utils.run_cmd(cmd)

    output_vcf = output_prefix + 'changes.vcf.gz'
    cmd = ['bcftools', 'view', '-i', consensus_filter, '-Oz',
           '--threads={0}'.format(multiprocessing.cpu_count()), output_bcf, '>',
           output_vcf]
    dx_utils.run_cmd(cmd)

    output = {}
    output['consensus_fasta'] = dx_utils.gzip_and_upload(output_fasta)
    output['output_numvar'] = dx_utils.gzip_and_upload(output_count)
    output['consensus_vcf'] = dxpy.dxlink(dxpy.upload_local_file(output_vcf))

    return output

dxpy.run()
