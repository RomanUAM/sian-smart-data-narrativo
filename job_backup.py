"""Optional private S3 snapshots; no credentials are included in exports."""
import os

def configured():return bool(os.environ.get('SIAN_BACKUP_BUCKET'))
def object_key(token):return os.environ.get('SIAN_BACKUP_PREFIX','sian/jobs').strip('/')+'/'+token+'.zip'
def checkpoint(job):
    if not configured():return False
    try:
        import boto3
        boto3.client('s3').put_object(Bucket=os.environ['SIAN_BACKUP_BUCKET'],Key=object_key(job.root.name),Body=job.archive(),ContentType='application/zip',ServerSideEncryption='AES256')
        job.set('backup_status','saved');return True
    except Exception as exc:
        job.set('backup_status','failed');job.log('Respaldo externo falló: '+type(exc).__name__);return False

def recover(token):
    if not configured():return None
    import boto3
    try:
        response=boto3.client('s3').get_object(Bucket=os.environ['SIAN_BACKUP_BUCKET'],Key=object_key(token))
        if response.get('ContentLength',0)>500_000_000:raise ValueError('Respaldo excede 500 MB.')
        return response['Body'].read(500_000_001)
    except boto3.client('s3').exceptions.NoSuchKey:return None
