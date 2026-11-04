"""Generate private, read-only source-derived CP candidate photos/clips.
Camera display time is not treated as a correct UTC clock. No identity-to-face joins.
Run with: uv run --with pillow python .../extract.py --stage pilot|all
"""
import argparse,os,collections,concurrent.futures,csv,datetime,hashlib,json,pathlib,re,subprocess
from PIL import Image,ImageDraw,ImageFont
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
MEDIA=HERE/'media'
CAL=json.loads((HERE/'clock-calibration.json').read_text())
OFFSET=datetime.timedelta(seconds=CAL['applied_offset_seconds'])
PILOTS={2607993,2608466,2608511,2608581,2608635}

def command(args,timeout=180):
 r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
 if r.returncode:raise RuntimeError('Command failed: '+r.stderr[-1800:])
 return r.stdout

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def parse(v):return datetime.datetime.fromisoformat(v)
def camera(cp):return parse(cp).replace(tzinfo=None)+OFFSET

manifest=json.loads((ROOT/'manifest.json').read_text())
files={re.search(r'_(\d\d)-(\d\d)',x['file']).group(0)[1:].replace('-',':'):x for x in manifest['files']}
index=json.loads((ROOT/'reverse-engineering/source-api-record-index.json').read_text())['records']
VIDEOS=[]
for x in index:
 a,b=parse(x['begin']),parse(x['end']);entry=files[a.strftime('%H:%M')]
 VIDEOS.append({'a':a,'b':b,'file':entry['file'],'path':ROOT/entry['file'],'sha256':entry['sha256']})
VIDEOS.sort(key=lambda x:x['a'])

def at(t):return next((v for v in VIDEOS if v['a']<=t<v['b']),None)
def segments(a,b):
 return [(v,max(a,v['a']),min(b,v['b'])) for v in VIDEOS if max(a,v['a'])<min(b,v['b'])]
def photo(t,out):
 v=at(t)
 if v is None:return None
 if not out.exists():command(['ffmpeg','-v','error','-threads','2','-ss',f"{(t-v['a']).total_seconds():.6f}",'-i',str(v['path']),'-frames:v','1','-q:v','2',str(out)])
 with Image.open(out) as im:assert im.size==(2880,1620),im.size
 return {'file':str(out.relative_to(HERE)),'camera_time':t.isoformat(),'source':v['file'],'nominal_source_offset_seconds':(t-v['a']).total_seconds(),'sha256':sha(out)}

def clip(center,out):
 start,end=center-datetime.timedelta(seconds=15),center+datetime.timedelta(seconds=15)
 parts=segments(start,end)
 expected=sum((b-a).total_seconds() for _,a,b in parts)
 assert abs(expected-30)<0.001,'Unavailable source coverage around candidate'
 if not out.exists():
  args=['ffmpeg','-v','error']
  for v,a,b in parts:args+=['-threads','2','-ss',f"{(a-v['a']).total_seconds():.6f}",'-t',f'{(b-a).total_seconds():.6f}','-i',str(v['path'])]
  graph=[]
  for i in range(len(parts)):graph.append(f'[{i}:v]setpts=PTS-STARTPTS,scale=1440:-2,setsar=1[v{i}]')
  if len(parts)==1:map_name='[v0]'
  else:
   graph.append(''.join(f'[v{i}]' for i in range(len(parts)))+f'concat=n={len(parts)}:v=1:a=0[out]');map_name='[out]'
  args+=['-filter_complex',';'.join(graph),'-map',map_name,'-an','-c:v','libx264','-threads','2','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
  command(args)
 meta=json.loads(command(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_name,width,height,codec_type','-of','json',str(out)]))
 assert len(meta['streams'])==1 and meta['streams'][0]['codec_name']=='h264'
 duration=float(meta['format']['duration']);assert abs(duration-30)<.2,duration
 log=out.with_suffix('.strict-decode.log')
 check=subprocess.run(['ffmpeg','-v','error','-xerror','-err_detect','explode','-threads','2','-i',str(out),'-map','0:v:0','-f','null','-'],capture_output=True,text=True,timeout=180)
 log.write_text(check.stderr);assert check.returncode==0 and check.stderr=='',check.stderr[-1000:]
 return {'file':str(out.relative_to(HERE)),'start_camera_time':start.isoformat(),'end_camera_time':end.isoformat(),'duration_seconds':duration,'muted':True,'strict_decode_verified':True,'sha256':sha(out),'segments':[{'source':v['file'],'start':a.isoformat(),'end':b.isoformat()} for v,a,b in parts]}

def storyboard(source,out):
 if out.exists():return str(out.relative_to(HERE))
 tiles=[]
 font=ImageFont.load_default(size=22)
 for i,offset in enumerate((-15,-10,-5,0,5,10,14.8)):
  p=out.parent/f'story-{i}.jpg'
  if not p.exists():command(['ffmpeg','-v','error','-threads','2','-ss',str(offset+15),'-i',str(source),'-frames:v','1','-vf','scale=960:-2','-q:v','2',str(p)])
  im=Image.open(p).convert('RGB');tile=Image.new('RGB',(960,578),'#111827');tile.paste(im,(0,0));ImageDraw.Draw(tile).text((12,547),f'Candidate offset {offset:+g}s (clock uncertainty +/-5s)',font=font,fill='white');tiles.append(tile)
 result=Image.new('RGB',(2880,1734),'#111827')
 for i,tile in enumerate(tiles):result.paste(tile,((i%3)*960,(i//3)*578))
 result.save(out,quality=92)
 return str(out.relative_to(HERE))

raw=json.loads((ROOT/'enpiso/.secrets/transaction-search-day30-all.json').read_text())
groups=collections.defaultdict(list)
for x in raw['records']:groups[x['headerHistoryId']].append(x)
events=[]
for header,members in groups.items():
 x=members[0]
 if x['deviceName']!=os.environ['CP_DEVICE_NAME'] or float(x['quantity'])<=0:continue
 assert x['moduleName']=='[WORKSHOP]' and x['startDate']=='2026-10-30'
 assert len({str(m['quantity']) for m in members})==1
 t=camera(x['endTime'])
 if not at(t):continue
 events.append({'history_header_id':header,'cp_start':x['startTime'],'cp_end_candidate':x['endTime'],'camera_start_candidate':camera(x['startTime']).isoformat(),'camera_end_candidate':t.isoformat(),'offset_seconds':CAL['applied_offset_seconds'],'clock_uncertainty_seconds':CAL['estimated_uncertainty_seconds'],'quantity_once_per_header':x['quantity'],'operation':x['operationName'],'device':x['deviceName'],'order':x['workOrderNumber'],'product':x['productCode'],'member_row_count':len(members),'pilot':header in PILOTS,'in_original_uncalibrated_16':x['endTime']>='2026-10-30 14:09:24','anchor_status':'interval-end hypothesis, not verified physical completion','physical_completion_verified':False})
events.sort(key=lambda x:x['cp_end_candidate'])
assert len(events)==40 and sum(x['in_original_uncalibrated_16'] for x in events)==16

def process(event):
 out=MEDIA/'events'/str(event['history_header_id']);out.mkdir(parents=True,exist_ok=True)
 previous=out/'asset-metadata.json'
 if previous.exists():
  old=json.loads(previous.read_text())
  for field in ('cp_end_candidate','camera_end_candidate','offset_seconds','clock_uncertainty_seconds'):
   assert old[field]==event[field],'Existing assets use another calibration; preserve them and choose a new output directory'
 t=parse(event['camera_end_candidate'])
 event['photo']=photo(t,out/'at-candidate.jpg')
 event['before_photo']=photo(t-datetime.timedelta(seconds=5),out/'before-5s.jpg')
 event['after_photo']=photo(t+datetime.timedelta(seconds=5),out/'after-5s.jpg')
 event['clip']=clip(t,out/'candidate-clip.mp4')
 if event['pilot']:
  event['storyboard']=storyboard(HERE/event['clip']['file'],out/'storyboard.jpg')
  a=parse(event['camera_start_candidate'])
  event['alternative_start_photo']=photo(a,out/'alternative-start.jpg')
  if segments(a-datetime.timedelta(seconds=15),a+datetime.timedelta(seconds=15)) and sum((b-s).total_seconds() for _,s,b in segments(a-datetime.timedelta(seconds=15),a+datetime.timedelta(seconds=15)))==30:
   event['alternative_start_clip']=clip(a,out/'alternative-start-clip.mp4')
  else:event['alternative_start_clip_unavailable']='Interval start precedes available source footage'
 (out/'asset-metadata.json').write_text(json.dumps(event,indent=2)+'\n')
 print('Verified candidate assets:',event['history_header_id'],event['cp_end_candidate'],'->',event['camera_end_candidate'],flush=True)
 return event

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stage',choices=['pilot','all'],required=True);args=p.parse_args()
 selected=[x for x in events if x['pilot']] if args.stage=='pilot' else events
 used={v['file']:v for e in selected for v,_,_ in segments(parse(e['camera_end_candidate'])-datetime.timedelta(seconds=15),parse(e['camera_end_candidate'])+datetime.timedelta(seconds=15))}
 for v in used.values():assert sha(v['path'])==v['sha256'],'Source hash mismatch'
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:completed=list(pool.map(process,selected))
 for v in used.values():assert sha(v['path'])==v['sha256'],'Source changed during extraction'
 output={'stage':args.stage,'events':completed,'calibration':CAL,'candidate_population':len(events),'previous_uncalibrated_population':16,'all_clip_strict_decodes_passed':True,'sources_unchanged':True,'anchor_semantics_confirmed':False,'physical_completion_proven':False,'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 (HERE/(args.stage+'-assets.json')).write_text(json.dumps(output,indent=2)+'\n')
 with (HERE/(args.stage+'-index.csv')).open('w',newline='') as f:
  keys=['history_header_id','cp_start','cp_end_candidate','camera_end_candidate','offset_seconds','clock_uncertainty_seconds','quantity_once_per_header','operation','device','order','product','member_row_count','pilot','in_original_uncalibrated_16','anchor_status','physical_completion_verified']
  writer=csv.DictWriter(f,fieldnames=keys+['photo','clip','storyboard'],lineterminator='\n');writer.writeheader()
  for e in completed:writer.writerow({**{k:e[k] for k in keys},'photo':e['photo']['file'],'clip':e['clip']['file'],'storyboard':e.get('storyboard','')})
 print('Completed',args.stage,len(completed),'candidates; completion semantics remain unproven.')
