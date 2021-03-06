import os
import subprocess
import glob
import dxpy

import dx_utils

BIONANO_ROOT = '/Solve3.2.1_04122018/'
SCRIPTS_DIR = os.path.join(BIONANO_ROOT, 'PIPELINE', 'Pipeline')

HYBRID_DIR = os.path.join(BIONANO_ROOT, 'HybridScaffold', '04122018')
TOOLS_DIR = os.path.join(BIONANO_ROOT, 'RefAligner', '7437.7523rel')


os.environ['PATH'] = HYBRID_DIR + \
    os.pathsep + os.environ['PATH']

# configure R library paths
os.link('/usr/lib/R/modules/lapack.so', '/usr/lib/R/lib/libRlapack.so')
os.link('/usr/lib/libblas.so', '/usr/lib/R/lib/libRblas.so')


def run_cmd(cmd, returnOutput=False):
    print cmd
    if returnOutput:
        output = subprocess.check_output(
            cmd, shell=True, executable='/bin/bash').strip()
        print output
        return output
    else:
        subprocess.check_call(cmd, shell=True, executable='/bin/bash')


def remove_special_chars(string):
    '''function that replaces any characters in a string that are not alphanumeric or _ or .'''
    string = "".join(
        char for char in string if char.isalnum() or char in ['_', '.'])

    return string


def download_and_gunzip_file(input_file, skip_decompress=False, additional_pipe=None):
    input_file = dxpy.DXFile(input_file)
    input_filename = input_file.describe()['name']
    ofn = remove_special_chars(input_filename)

    cmd = 'dx download ' + input_file.get_id() + ' -o - '
    if input_filename.endswith('.tar.gz'):
        ofn = 'tar_output_{0}'.format(ofn.replace('.tar.gz', ''))
        cmd += '| tar -zxvf - '
    elif (os.path.splitext(input_filename)[-1] == '.gz') and not skip_decompress:
        cmd += '| gunzip '
        ofn = os.path.splitext(ofn)[0]
    if additional_pipe is not None:
        cmd += '| ' + additional_pipe
    cmd += ' > ' + ofn
    print cmd
    subprocess.check_call(cmd, shell=True)

    return ofn


@dxpy.entry_point("main")
def main(**job_inputs):
    bionano_cmap_1_link = job_inputs['bng_enzyme1']
    bionano_cmap_2_link = job_inputs['bng_enzyme2']
    ngs_fasta_link = job_inputs['ngs_fasta_or_cmap']
    args_xml_link = job_inputs.get('args_xml')

    # Download all the inputs
    bionano_cmap_1_filename = os.path.join(
        '/home/dnanexus', download_and_gunzip_file(bionano_cmap_1_link))
    bionano_cmap_2_filename = os.path.join(
        '/home/dnanexus', download_and_gunzip_file(bionano_cmap_2_link))
    ngs_fasta_filename = os.path.join('/home/dnanexus', download_and_gunzip_file(ngs_fasta_link))

    if args_xml_link:
        args_xml_filename = download_and_gunzip_file(args_xml_link)
    else:
        args_xml_filename = os.path.join(HYBRID_DIR, 'TGH', 'hybridScaffold_two_enzymes.xml')
    output_dir = "hybrid_scaffold_output"

    run_cmd('mkdir {0}'.format(output_dir))
    results_tar = output_dir + '_results.tar'

    cmd = "Rscript {dir}/runTGH.R --help".format(dir=HYBRID_DIR)
    run_cmd(cmd)

    scaffold_cmd = ("Rscript {dir}/runTGH.R -N {ngs_fasta} "
                    "-b1 {bng1} -b2 {bng2} -O {outdir} -R {refaligner} -t {results} "
                    .format(dir=HYBRID_DIR, ngs_fasta=ngs_fasta_filename, bng1=bionano_cmap_1_filename,
                            bng2=bionano_cmap_2_filename, outdir=output_dir,
                            refaligner=os.path.join(TOOLS_DIR, 'RefAligner'), results=results_tar))
    scaffold_cmd += '-e1 {enzyme1} -e2 {enzyme2} '.format(
        enzyme1=job_inputs['enzyme1_name'], enzyme2=job_inputs['enzyme2_name'])

    if job_inputs.get("cuts1_file") and job_inputs.get("cuts2_file"):
        cuts1_file = download_and_gunzip_file(job_inputs["cuts1_file"])
        cuts2_file = download_and_gunzip_file(job_inputs["cuts2_file"])
        scaffold_cmd += '-m1 {cuts1} -m2 {cuts2} '.format(cuts1=cuts1_file, cuts2=cuts2_file)

    scaffold_cmd += ' {args_xml}'.format(args_xml=args_xml_filename)
    run_cmd(scaffold_cmd)

    scaffold_final = glob.glob(
        os.path.join(output_dir, 'TGH_M1', 'AGPExport', '*HYBRID*'))

    if not scaffold_final:
        print("ERROR: No hybrid scaffolds produced.")
        hybrid_scaffold_log = os.path.join(output_dir, 'TGH.log')
        run_cmd('tail -n 50 {0}'.format(hybrid_scaffold_log))
    
    scaffold_final_ncbi = glob.glob(
        os.path.join(output_dir, 'hybrid_scaffolds*', '*_HYBRID_SCAFFOLD_NCBI.fasta'))
    unscaffolded_final = glob.glob(
        os.path.join(output_dir, 'hybrid_scaffolds*', '*_HYBRID_SCAFFOLD_NOT_SCAFFOLDED.fasta'))
    output = {
        "scaffold_fasta": [dxpy.dxlink(dxpy.upload_local_file(f)) for f in scaffold_final if f.endswith(".fasta")],
        "scaffold_output": [dxpy.dxlink(dxpy.upload_local_file(f)) for f in scaffold_final],
        "ncbi_scaffold_final": dx_utils.gzip_and_upload(scaffold_final_ncbi[0]),
        "unscaffolded_final": dx_utils.gzip_and_upload(unscaffolded_final[0])
        }
    
    tar_name = "hybrid_scaffold_output.tar.gz"
    tar_cmd = "tar czvf {tar_name} {outdir}".format(
        tar_name=tar_name,
        outdir=output_dir)
    run_cmd(tar_cmd)
    output_id = dxpy.upload_local_file(tar_name)

    output["scaffold_targz"] = dxpy.dxlink(output_id)

    return output