"""Fetch only the branch 13/company 1, requested Nov 3 data."""
params={'company_id':1,'branch_id':13,'from':'2026-11-03','to':'2026-11-03','per_page':100,'page':1,'return_full_objects':1}
for endpoint in ['/invoices','/orders']:
    values=[];page=1
    while True:
        d=get(endpoint,dict(params,page=page))
        store(out/(endpoint[1:]+f'-2026-11-03-page-{page}.json'),d)
        print(endpoint,'page',page,'metadata',{k:v for k,v in d.items() if k not in ['data','results'] and not isinstance(v,(dict,list))})
        data=rows(d);values.extend(data)
        if not data or page>=int(d.get('last_page',1)):break
        page+=1
        if page>30:raise RuntimeError('Unexpected pagination; stop')
    print(endpoint,'row count',len(values))
    if values:
        r=values[0];print('Field names',list(r));print('Non-PII sample',{k:v for k,v in r.items() if k in ['id','company_id','branch_id','date','created_at','updated_at','invoice_date','status','type','operation_type','order_type','total','subtotal','total_amount','discount','discount_amount','tax','tax_amount','currency_code','payment_status','time','start_time','end_time']})
        for key in ['details','items','invoice_details','order_details','payments','employees']:
            if key in r:
                value=r[key];print(key,'type',type(value).__name__,'count',len(value) if isinstance(value,(list,dict)) else None)
                if isinstance(value,list) and value:print(key,'field names',list(value[0]))
    store(out/(endpoint[1:]+'-2026-11-03.json'),values)
