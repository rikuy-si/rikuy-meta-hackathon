"""Build demo/data.json from the evidence files (POS private export + vision tracks). Clients reduced to initials."""
from pathlib import Path
import json,os,datetime as dt
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'outputs/pos-private'
O=json.loads((P/'orders-2026-11-03.json').read_text());I=json.loads((P/'invoices-2026-11-03.json').read_text())
sod=lambda hhmmss:sum(int(v)*m for v,m in zip(hhmmss.split(':'),(3600,60,1)))
clk=lambda s:f'{int(s)//3600:02}:{int(s)%3600//60:02}:{int(s)%60:02}'
u2l=lambda s:(dt.datetime.fromisoformat(s.replace('Z','+00:00'))-dt.timedelta(hours=4)).strftime('%H:%M:%S')
order=next(o for o in O if o['number']=='2026-4872')
invs=[i for i in I if i.get('order_id')==order['id']]
ok=next(i for i in invs if i['status']=='Completed');void=[i for i in invs if i['status']=='Cancelled']
prov=[o for o in O if any(os.environ['POS_PROVIDER'] in ((d.get('supplier') or {}).get('name') or '') for d in o['order_details'])]
prov_before=[o['number'] for o in prov if o['created_at'][11:19]<'11:13:02']
man=json.loads((ROOT/'outputs/provider-stable/case0-man.json').read_text())['track']
man=[x['sod'] for x in man if x['kind']=='observed' and (x.get('score') or 0)>.045 and (x['box'][1]+x['box'][3])/2<.25]
rv=json.loads((ROOT/'outputs/reid-407/review-layer.json').read_text())
samp=json.loads((ROOT/'outputs/sam-provider/provider-sam-layer.json').read_text())['observed']
v=json.loads((ROOT/'demo/video.json').read_text()) if (ROOT/'demo/video.json').exists() else {'t0_sod':39940.0,'speed':12.0}
c=order.get('client') or {};ini=(c.get('name') or '?')[:1]+'. '+(c.get('last_name') or '?')[:1]+'.'
m0,m1=min(man),max(man)
w_first=rv['tracklets'][0]['start_sod'];w_bed0=40462.0;w_bed1=40824.0;w_rec=40883.0;w_last=rv['tracklets'][-1]['end_sod']
pos_open=sod(order['created_at'][11:19]);pos_close=sod(u2l(order['completed_at']));pay=ok['invoice_payments'][0]
line=ok['invoice_details'][0]
PAY={'Efectivo':('cash','efectivo'),'CardNet':('card (CardNet)','tarjeta (CardNet)')}
pen,pes=PAY.get(pay['name'],(pay['name'],pay['name']))
events=[
 {'sod':m0,'src':'vision','who':'c1','en':'Client 1 sits at the workstation','es':'Cliente 1 se sienta en la estación'},
 {'sod':m0+40,'src':'vision','who':'p','en':'Provider works on client 1','es':'La prestadora atiende al cliente 1'},
 {'sod':w_first,'src':'vision','who':'c2','en':'Client 2 arrives at the front desk','es':'Clienta 2 llega a recepción'},
 {'sod':pos_open,'src':'pos','who':'c2','en':f"Turn {order['number']} opened · {line['description']} · Provider",'es':f"Turno {order['number']} abierto · {line['description']} · Provider"},
 {'sod':pos_open+1,'src':'pos','who':'c2','en':f"Invoice {ok['number']} · RD${ok['total_amount']:.0f} · paid in {pen} at arrival",'es':f"Factura {ok['number']} · RD${ok['total_amount']:.0f} · pagada en {pes} al llegar"},
 {'sod':m1,'src':'vision','who':'c1','en':'Client 1 leaves the workstation','es':'Cliente 1 deja la estación'},
 {'sod':m1+1,'src':'pos','who':'c1','en':'No POS ticket for Provider covers client 1','es':'Ningún ticket del POS de Provider cubre al cliente 1','flag':True},
 {'sod':w_bed0,'src':'vision','who':'c2','en':'Client 2 on the bed · service starts','es':'Clienta 2 en la camilla · empieza el servicio'},
 {'sod':w_bed1,'src':'vision','who':'c2','en':'Client 2 gets up · service ends','es':'Clienta 2 se levanta · termina el servicio'},
 {'sod':w_rec,'src':'vision','who':'c2','en':'Client 2 back at the front desk','es':'Clienta 2 vuelve a recepción'},
 {'sod':w_last,'src':'vision','who':'c2','en':'Client 2 leaves the view','es':'Clienta 2 sale de la vista'},
 {'sod':pos_close,'src':'pos','who':'c2','en':f"Turn {order['number']} closed",'es':f"Turno {order['number']} cerrado"},
]
for e in events:e['clock']=clk(e['sod']);e['vt']=round((e['sod']-v['t0_sod'])/v['speed'],2)
data={'store':'Rostro Perfecto','date':'2026-11-03','camera':'Camera 6','provider':{'name':'the provider','name_source':'pos'},
 'cases':[
  {'id':'c1','label_en':'Client 1 · Mr.','label_es':'Cliente 1 · Sr.','service_seen':[clk(m0),clk(m1)],'service_seconds':round(m1-m0),'pos':None,
   'pos_note_en':f"No POS ticket for Provider before 11:13:02 today ({len(prov_before)} found). Check if it was billed under another turn or provider.",
   'pos_note_es':f"No hay ticket del POS de Provider antes de las 11:13:02 hoy ({len(prov_before)} encontrados). Revisar si se cobró en otro turno o con otra prestadora."},
  {'id':'c2','label_en':f'Client 2 · Ms. {ini}','label_es':f'Clienta 2 · Sra. {ini}','arrive':clk(w_first),'bed':[clk(w_bed0),clk(w_bed1)],'service_seconds':round(w_bed1-w_bed0),
   'provider_hands_on':[samp['first'],samp['last']],'leave':clk(w_last),'visit_seconds':round(w_last-w_first),
   'pos':{'turn':order['number'],'invoice':ok['number'],'service':line['description'],'provider':'Provider','amount':ok['total_amount'],'currency':'DOP','payment':pay['name'],'payment_en':pen.capitalize(),'payment_es':pes.capitalize(),'opened':clk(pos_open),'closed':clk(pos_close),'turn_seconds':round(pos_close-pos_open),'voided_invoices':[x['number'] for x in void],'voided_at':u2l(void[0]['updated_at']) if void else None}}],
 'changeover_seconds':round(w_bed0-m1),'events':events,
 'notes':{'pos_time':'POS created_at is local time; completed_at is UTC (minus 4 h).','identity':'Names come from the POS. The video shows where people are, not who they are. No face recognition; client faces blurred.'}}
(ROOT/'demo/data.json').write_text(json.dumps(data,indent=2,ensure_ascii=False));print(json.dumps({k:data[k] for k in ['cases','changeover_seconds']},indent=1,ensure_ascii=False))
