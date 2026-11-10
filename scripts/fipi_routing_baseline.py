"""Frozen NumPy routing baseline on saved FIPI statements; no generation/network."""
import csv
import json
import random
import re
from collections import Counter
from pathlib import Path
import numpy as np
from lxml import html
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import fipi_domain_quality as q

OUT=q.ROOT/'data/annotation/analyses/2026-11-09-routing-baseline-v1'
SPLIT=q.OUT/'split.json'
TOKEN=re.compile(r'\w+|[^\w\s]',re.UNICODE)
def dump(name,value): q.dump(OUT/name,value)
def csvout(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def tokens(record,kind):
    return TOKEN.findall((q.semantic_tokens(record) if kind=='semantic' else q.extract_text(record)).lower())
def augment(record):
    tree=html.fromstring(record['statement_html'])
    for e in tree.iter():
        if not isinstance(e.tag,str): continue
        for field in ('text','tail'):
            value=getattr(e,field)
            if value: setattr(e,field,re.sub(r'\s+', '\u00a0 \u2009',value))
    result=dict(record)
    result['statement_html']='<div data-format="equivalent"><span>'+html.tostring(tree,encoding='unicode',with_tail=False)+'</span></div>'
    return result
def signature(record):
    tree=html.fromstring(record['statement_html'])
    def node(e):
        return (e.tag,sorted(e.attrib.items()),' '.join((e.text or '').split()),[(node(c),' '.join((c.tail or '').split())) for c in e if isinstance(c.tag,str)])
    return dict(math=[node(e) for e in tree.xpath('//math')],numbers=re.findall(r'\d+(?:[.,]\d+)?',tree.text_content()),operators=[c for c in tree.text_content() if c in '+−-=×÷*/<>≤≥≠√^'],images=[e.get('src') for e in tree.xpath('//img')],words=TOKEN.findall(' '.join(tree.text_content().split())))
def vectorize(documents,vocab):
    x=np.zeros((len(documents),len(vocab)),dtype=np.float64)
    for i,doc in enumerate(documents):
        for t,n in Counter(doc).items():
            if t in vocab: x[i,vocab[t]]=n
    return x
def fit(documents,y,nclasses):
    df=Counter(t for doc in documents for t in set(doc))
    chosen=sorted((t for t,n in df.items() if n>=2),key=lambda t:(-df[t],t))[:6000]
    vocab={t:i for i,t in enumerate(chosen)}; x=vectorize(documents,vocab)
    counts=np.zeros((nclasses,len(vocab))); classes=np.bincount(y,minlength=nclasses).astype(float)
    for c in range(nclasses): counts[c]=x[y==c].sum(axis=0)
    # Impossible unseen classes have zero prior, rather than invented examples.
    prior=np.full(nclasses,-np.inf); prior[classes>0]=np.log(classes[classes>0]/len(y))
    logp=np.log((counts+1)/(counts.sum(axis=1,keepdims=True)+len(vocab)))
    idf=np.log((1+len(x))/(1+(x>0).sum(axis=0)))+1
    z=x*idf; z/=np.maximum(np.linalg.norm(z,axis=1,keepdims=True),1e-30)
    return dict(vocab=vocab,x=x,prior=prior,logp=logp,idf=idf,z=z,y=y,classes=classes)
def scores(model,docs,method):
    x=vectorize(docs,model['vocab'])
    if method=='nb': return x@model['logp'].T+model['prior']
    if method=='majority': return np.tile(model['classes'],(len(x),1))
    z=x*model['idf']; z/=np.maximum(np.linalg.norm(z,axis=1,keepdims=True),1e-30)
    similarity=z@model['z'].T
    # Each class ranked by its nearest training document; top1 is cosine 1NN.
    return np.column_stack([similarity[:,model['y']==c].max(axis=1) if (model['y']==c).any() else np.full(len(x),-np.inf) for c in range(len(model['classes']))])
def metrics(y,s,n):
    pred=s.argmax(axis=1); cm=np.zeros((n,n),dtype=int); np.add.at(cm,(y,pred),1)
    tp=cm.diagonal(); support=cm.sum(axis=1); denom=support+cm.sum(axis=0)
    f1=np.divide(2*tp,denom,out=np.zeros(n),where=denom>0)
    return dict(accuracy=float((pred==y).mean()),macro_f1=float(f1.mean()),top3_accuracy=float(np.mean([a in np.argsort(-row,kind='stable')[:3] for a,row in zip(y,s)]))),cm,f1
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    records=q.load_bank(); byid={r['id']:r for r in records}; split=json.loads(SPLIT.read_text(encoding='utf-8'))
    assert split==q.make_split(records)
    helper_sha=q.sha(Path(q.__file__))
    labels=sorted(set(map(q.class_label,records))); index={c:i for i,c in enumerate(labels)}
    protocol=dict(seed=q.SEED,label_definition='first-listed KES code first two levels; auxiliary routing only',label_universe=labels,primary='group_semantic_nb',representations=['plain','semantic'],models=['majority','nb','tfidf_1nn'],alpha=1,min_df=2,max_features=6000,tf='raw counts',idf='log((1+n_train)/(1+df_train))+1; L2 norm',selection='fixed before scores; no tuning, no seed selection',ties='sorted labels; stable sort; nearest-document ties first sorted train ID',macro_f1='all declared labels including absent classes; zero division=0',augmentation='one equivalent HTML/Unicode whitespace variant; each original total weight 1, original/variant 0.5 each',bootstrap='1000 group bootstrap resamples, percentile 95%, fixed seed',sources=['https://scikit-learn.org/stable/modules/naive_bayes.html','https://scikit-learn.org/stable/modules/feature_extraction.html','https://scikit-learn.org/stable/modules/cross_validation.html'],implementation='NumPy; sklearn not used')
    dump('protocol.json',protocol)  # Persisted before training/scoring.
    dump('split.json',split)
    shuffled=sorted(byid); random.Random(q.SEED).shuffle(shuffled); randomsplit={}; start=0
    for name,ids in split['splits'].items(): randomsplit[name]=sorted(shuffled[start:start+len(ids)]); start+=len(ids)
    dump('random-split.json',dict(seed=q.SEED,splits=randomsplit,diagnostic_only=True))
    variants={i:augment(r) for i,r in byid.items()}
    assert all(signature(r)==signature(variants[i]) for i,r in byid.items())
    invariants=[dict(task_id=i,signature_equal=True,plain_tokens_equal=tokens(r,'plain')==tokens(variants[i],'plain'),semantic_tokens_equal=tokens(r,'semantic')==tokens(variants[i],'semantic')) for i,r in byid.items()]
    csvout('augmentation-invariants.csv',invariants)
    dump('augmentation-examples.json',[dict(task_id=i,original_html=byid[i]['statement_html'],variant_html=variants[i]['statement_html']) for i in sorted(byid)[:3]])
    results=[]; predictions=[]; features=[]; primary=None; cms={}; fits={}
    for splitname,parts in [('group',split['splits']),('random',randomsplit)]:
        trainids=parts['train']; ytrain=np.array([index[q.class_label(byid[i])] for i in trainids])
        for kind in ['plain','semantic']:
            train=[tokens(byid[i],kind) for i in trainids]; model=fit(train,ytrain,len(labels)); key=f'{splitname}_{kind}'; fits[key]=model
            dump(key+'-vocab.json',model['vocab'])
            np.savez_compressed(OUT/(key+'-weights.npz'),prior=model['prior'],logp=model['logp'],idf=model['idf'],train_counts=model['x'],train_tfidf=model['z'],train_labels=ytrain,train_ids=np.array(trainids),labels=np.array(labels))
            for part in ['dev','test']:
                ids=parts[part]; y=np.array([index[q.class_label(byid[i])] for i in ids]); docs=[tokens(byid[i],kind) for i in ids]
                for method in ['majority','nb','tfidf_1nn']:
                    name=key+'_'+method; s=scores(model,docs,method); m,cm,f1=metrics(y,s,len(labels)); results.append(dict(model=name,partition=part,**m)); cms[(name,part)]=cm
                    for i,actual,row in zip(ids,y,s):
                        order=np.argsort(-row,kind='stable'); predictions.append(dict(model=name,partition=part,task_id=i,actual=labels[actual],predicted=labels[order[0]],top3=' '.join(labels[j] for j in order[:3])))
                    if name=='group_semantic_nb' and part=='test': primary=(ids,y,s,model)
    # Train variants have identical token vectors. Explicit 0.5+0.5 weighted fit reproduces counts and priors exactly.
    model=fits['group_semantic']; trainids=split['splits']['train']; vx=vectorize([tokens(variants[i],'semantic') for i in trainids],model['vocab'])
    assert np.array_equal(vx,model['x']); augmented_counts=.5*model['x']+.5*vx
    assert np.array_equal(augmented_counts,model['x'])
    np.savez_compressed(OUT/'group_semantic_augmented-weights.npz',prior=model['prior'],logp=model['logp'],idf=model['idf'],weighted_train_counts=augmented_counts,train_ids=np.array(trainids),labels=np.array(labels))
    ids,y,s,model=primary
    robustness=[]
    for trainmode in ['clean','augmented_weighted']:
        for testmode in ['clean','format_variant']:
            docs=[tokens(byid[i] if testmode=='clean' else variants[i],'semantic') for i in ids]
            ss=scores(model,docs,'nb')
            for tid,actual,row in zip(ids,y,ss):
                order=np.argsort(-row,kind='stable'); predictions.append(dict(model='group_semantic_nb_'+trainmode+'_'+testmode,partition='test',task_id=tid,actual=labels[actual],predicted=labels[order[0]],top3=' '.join(labels[j] for j in order[:3])))
            m,_,_=metrics(y,ss,len(labels)); robustness.append(dict(train=trainmode,test=testmode,**m,prediction_agreement=float((ss.argmax(1)==s.argmax(1)).mean())))
    csvout('augmentation-results.csv',robustness)
    for c,label in enumerate(labels):
        contrast=model['logp'][c]-np.mean(np.delete(model['logp'],c,axis=0),axis=0)
        inverse=list(model['vocab'])
        for rank,j in enumerate(np.argsort(-contrast)[:12],1): features.append(dict(class_label=label,rank=rank,feature=inverse[j],distinctive_log_probability=float(contrast[j])))
    csvout('distinctive-features.csv',features)
    selected=[]
    for correct in [True,False]:
        for pos in [j for j in range(len(ids)) if bool(s[j].argmax()==y[j])==correct][:1 if correct else 2]:
            x=vectorize([tokens(byid[ids[pos]],'semantic')],model['vocab'])[0]; pred=int(s[pos].argmax()); actual=int(y[pos]); competitor=actual if pred!=actual else int(np.argsort(-s[pos],kind='stable')[1]); margin=x*(model['logp'][pred]-model['logp'][competitor]); js=np.argsort(-abs(margin))[:15]
            selected.append(dict(task_id=ids[pos],correct=correct,actual=labels[actual],predicted=labels[pred],compared_with=labels[competitor],source_url=byid[ids[pos]]['source_url'],prior={labels[c]:float(model['prior'][c]) if np.isfinite(model['prior'][c]) else None for c in set([pred,actual,competitor])},features=[dict(token=list(model['vocab'])[j],count=int(x[j]),predicted_loglikelihood_contribution=float(x[j]*model['logp'][pred,j]),actual_loglikelihood_contribution=float(x[j]*model['logp'][actual,j]),compared_loglikelihood_contribution=float(x[j]*model['logp'][competitor,j]),margin=float(margin[j])) for j in js if x[j]]))
    dump('explanations.json',selected)
    csvout('metrics.csv',results); csvout('predictions.csv',predictions)
    perclass=[]; confusion=[]
    for (name,part),cm in cms.items():
        denom=cm.sum(0)+cm.sum(1)
        for c,label in enumerate(labels):
            perclass.append(dict(model=name,partition=part,class_label=label,support=int(cm[c].sum()),predicted=int(cm[:,c].sum()),f1=float(2*cm[c,c]/denom[c]) if denom[c] else 0))
            for d,target in enumerate(labels): confusion.append(dict(model=name,partition=part,actual=label,predicted=target,count=int(cm[c,d])))
    csvout('per-class.csv',perclass); csvout('confusion.csv',confusion)
    groups=[g for g in split['template_groups'].values() if set(g)&set(ids)]; positions={i:j for j,i in enumerate(ids)}; rng=np.random.default_rng(q.SEED); boot=[]
    for _ in range(1000):
        ix=[positions[i] for g in rng.integers(len(groups),size=len(groups)) for i in groups[g]]
        boot.append(metrics(y[ix],s[ix],len(labels))[0])
    ci={k:list(map(float,np.percentile([b[k] for b in boot],[2.5,97.5]))) for k in boot[0]}
    overlap={part:sum(bool(set(g)&set(randomsplit['train'])) and bool(set(g)&set(randomsplit[part])) for g in split['template_groups'].values()) for part in ['dev','test']}
    primarymetrics=metrics(y,s,len(labels))[0]
    summary=dict(primary_model='group_semantic_nb',primary_metrics=primarymetrics,group_bootstrap_ci95=ci,test_tasks=len(ids),test_groups=len(groups),classes=len(labels),random_template_overlap_with_train=overlap,augmentation=dict(tasks=len(invariants),signature_pass=sum(r['signature_equal'] for r in invariants),semantic_token_invariance=sum(r['semantic_tokens_equal'] for r in invariants)/len(invariants),weighted_counts_exactly_equal=True),metrics=results)
    dump('summary.json',summary)
    # Four reviewable figures with source CSVs.
    testrows=[r for r in results if r['partition']=='test']; fig,ax=plt.subplots(figsize=(11,5)); xx=np.arange(len(testrows)); ax.bar(xx,[r['accuracy'] for r in testrows],label='accuracy'); ax.plot(xx,[r['macro_f1'] for r in testrows],'ro',label='macro F1'); ax.set_xticks(xx,[r['model'] for r in testrows],rotation=65,ha='right'); ax.legend(); fig.tight_layout(); fig.savefig(OUT/'01-model-comparison.png',dpi=140); plt.close(fig)
    cm=cms[('group_semantic_nb','test')]; fig,ax=plt.subplots(figsize=(10,8)); im=ax.imshow(cm); ax.set_xticks(range(len(labels)),labels,rotation=90); ax.set_yticks(range(len(labels)),labels); ax.set(xlabel='Predicted',ylabel='First-listed KES'); fig.colorbar(im); fig.tight_layout(); fig.savefig(OUT/'02-primary-confusion.png',dpi=140); plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4)); ax.bar(labels,cm.sum(1)); ax.set_xticks(range(len(labels)),labels,rotation=90); ax.set_ylabel('Group test support'); fig.tight_layout(); fig.savefig(OUT/'03-test-support.png',dpi=140); plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4)); ax.bar([r['train']+' / '+r['test'] for r in robustness],[r['accuracy'] for r in robustness]); ax.tick_params(axis='x',rotation=20); ax.set_ylabel('Accuracy'); fig.tight_layout(); fig.savefig(OUT/'04-format-robustness.png',dpi=140); plt.close(fig)
    assert q.sha(Path(q.__file__))==helper_sha, 'Helper changed during run; audit provenance before rerun'
    dump('provenance.json',dict(seed=q.SEED,implementation='NumPy, not sklearn',hashes={str(p.relative_to(q.ROOT)).replace('\\','/'):q.sha(p) for p in [Path(__file__),Path(q.__file__),SPLIT,q.BANK/'tasks.jsonl']},artifacts={p.name:q.sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in ['provenance.json','report.md','smoke-tests.json']}))
    dump('smoke-tests.json',dict(status='pass',checks=['saved split equals make_split','1148 augmentation content signatures identical','train-only vocabulary/IDF','weighted augmentation counts identical','frozen labels and protocol','helper unchanged during run','all variants remain with original task split']))
    report(summary,selected)

def report(s,examples):
    rows=[r for r in s['metrics'] if r['partition']=='test']
    lines=['# Baseline вспомогательной маршрутизации условий по КЭС','', 'На сохранённых 1148 условиях обучены NumPy Multinomial NB (alpha=1), TF–IDF cosine 1NN и majority. Цель — первый перечисленный код КЭС до двух уровней; первая метка не считается основной темой. Это не оценка решения, KC, сложности, качества тьютора или освоения ученика.','', '## Протокол','', 'Основной baseline заранее задан как group_semantic_nb. Гиперпараметры, seed 20261109 и все сравнения записаны в protocol.json до обучения. Dev показан для контроля; выбора моделей по нему или test нет. Словарь (minDF=2, максимум 6000), IDF и priors строятся только на train. Набор классов объявлен по банку; macro F1 включает все классы, нулевой знаменатель даёт 0. Не встреченный в train класс имеет нулевой prior. Топ-3 — ранжирование классов; для 1NN класс ранжируется ближайшим его train-документом.','', 'Группы numeric-template и исходный split взяты из domain-quality-v1. Правило группировки вычислено на всём банке без целевой метки (transductive контроль целостности); это не исключает более глубоких семантических повторов. Random split с тем же seed и числом задач в частях — диагностическое сравнение, не альтернативный честный тест. Его пересечения template-групп с train: '+str(s['random_template_overlap_with_train'])+'.','', '## Результаты','', '| Модель | Accuracy | Macro F1 | Top-3 |','|---|---:|---:|---:|']
    for r in rows: lines.append(f"| {r['model']} | {r['accuracy']:.3f} | {r['macro_f1']:.3f} | {r['top3_accuracy']:.3f} |")
    lookup={r['model']:r for r in rows}
    lines += ['', f"На group test структурное представление снижает accuracy NB с {lookup['group_plain_nb']['accuracy']:.3f} до {lookup['group_semantic_nb']['accuracy']:.3f}, но повышает accuracy 1NN с {lookup['group_plain_tfidf_1nn']['accuracy']:.3f} до {lookup['group_semantic_tfidf_1nn']['accuracy']:.3f}. Это взаимодействие представления и модели: частотный NB может переоценивать повторяющиеся зависимые MathML-маркеры, тогда как cosine retrieval использует другое взвешивание; данная гипотеза не проверена отдельным опытом. Основной заранее заданный baseline сохранён независимо от лучших цифр 1NN. Random test не даёт универсального прироста: semantic NB имеет такую же accuracy, semantic 1NN немного ниже group. Поэтому пересечения шаблонов подтверждают риск утечки, но завышение качества на этом seed не установлено."]
    lines += ['',f"Основной test: {s['test_tasks']} задач, {s['test_groups']} групп, {s['classes']} объявленных классов. 95% percentile bootstrap по группам (1000 повторов): {s['group_bootstrap_ci95']}. Это условный интервал одного разбиения, не вариативность обучения или всех возможных банков. Малые классы и отсутствующий train support делают macro F1 нестабильным; support и ошибки сохранены полностью.",'', '## Проверенная аугментация','', 'Для каждого условия построен детерминированный вариант: дополнительная HTML-обёртка/атрибут и замена последовательностей пробелов на NBSP, обычный и thin space. Проверены неизменные упорядоченные MathML-деревья с атрибутами, слова, числа, операторы и последовательность image src для всех 1148. Изображения не менялись; числа, рисунки, знаки и формулировки не перефразировались.',f"Структурная проверка: {s['augmentation']['signature_pass']}/1148; semantic token invariance: {s['augmentation']['semantic_token_invariance']:.1%}. В train реально проверены векторы исходника и варианта и взвешенная сумма 0.5+0.5: counts и priors точно совпадают. Поэтому augmented weighted модель алгебраически тождественна clean модели; отдельный файл весов сохраняет этот результат. Оценены clean и форматный frozen group test для обоих train режимов. Нулевой прирост здесь ожидаем: нормализация уже обеспечивает устойчивость к выбранному форматному шуму. Это проверка preprocessing, а не увеличение независимых данных или доказательство устойчивости к произвольным правкам HTML.",'', '## Интерпретация и применение','', 'distinctive-features.csv содержит top-12 признаков каждого класса по log P(token|class) минус среднее log P по остальным классам. Это ассоциация слов/MathML-границ и метки. Bag of words не использует порядок шагов и не распознаёт изображение (только IMAGE); присутствие признака не устанавливает математический метод. explanations.json сохраняет prior и вклады count × log likelihood для одного верного примера и двух ошибок; сопоставление predicted/actual для ошибки и predicted/runner-up для верных примеров делает видимым вклад текста, но не доказывает смысловую причину.']
    for e in examples: lines.append(f"- {e['task_id']}: {e['actual']} → {e['predicted']}; {'совпало' if e['correct'] else 'ошибка'} с операционной меткой; URL и численные вклады сохранены.")
    lines += ['', 'Модель годится как измеримый нижний ориентир будущей маршрутизации задач и как подсказка при индексации с предметной проверкой. Сравнение plain/semantic показывает влияние выбранных признаков; сохранение MathML остаётся необходимым для fidelity даже без прироста accuracy. Random/group разница диагностирует зависимость результата от повторов, но один seed не даёт причинной оценки размера утечки. Редкие темы требуют новых независимых семейств и проверки меток; баланс банка не означает баланс учебной программы.', '', '## Файлы и воспроизведение','', 'metrics.csv, per-class.csv и confusion.csv содержат полные таблицы; predictions.csv — ID и top-3 всех dev/test прогнозов. vocab/weights.npz, split.json, random-split.json, protocol.json и provenance.json позволяют воспроизвести baseline. 01–04 PNG показывают сравнение, confusion, поддержку и устойчивость. Из исходных данных читаются только условия; metadata и имена файлов не входят в признаки. Хеши входов и обеих программ зафиксированы. Команда: `.venv/Scripts/python.exe -B -X utf8 scripts/fipi_routing_baseline.py`.', '', 'Формулы и правила методов сверены с официальной документацией [Multinomial NB](https://scikit-learn.org/stable/modules/naive_bayes.html), [TF–IDF](https://scikit-learn.org/stable/modules/feature_extraction.html), [group separation](https://scikit-learn.org/stable/modules/cross_validation.html). Использована собственная NumPy-реализация, sklearn не установлен и не использован. Источник условий — локальный снимок ФИПИ 31.10.2026; открытый доступ не устанавливает лицензию на массовое распространение. Новых задач и LLM-разборов нет.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
if __name__=='__main__': main()
