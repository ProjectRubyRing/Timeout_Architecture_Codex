"""Build a local, macro-free XLSX and matching self-contained Markdown report."""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from datetime import datetime

import xlsxwriter
from xlsxwriter.utility import xl_rowcol_to_cell
from PIL import ImageFont

from report_data import (
    DATE, TITLE, SUBTITLE, SOURCES, PARAMS, SECTIONS, BUDGET,
    SCENARIOS, HISTORY, GLOSSARY, MONITORING, CHECKS, EXAMPLES,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)
STEM = f'AWS_Timeout_Design_{DATE}'
XLSX = OUT / (STEM + '.xlsx')
MD = OUT / (STEM + '.md')
SOURCE_MAP = {s[0]: s for s in SOURCES}
SECTION_MAP = {s['sheet']: s for s in SECTIONS}
GROUP_SHEETS = {
    '通信経路': '05_通信経路の動作',
    'JBoss・Java': '06_JBossとJavaの動作',
    'RDS Proxy': '07_Proxyの動作',
    'MySQL・Aurora': '08_DBの動作',
}
NAV = [
    ('00_読み方', '全体の案内と読み順'),
    ('01_結論と前提', '推奨初期値・仮定・未検証範囲'),
    ('02_構成と担当', '各機器と設定担当の関係'),
    ('02a_構成図', 'HTTP経路とDB経路・2種類の時計'),
    ('03_時計の原理', 'たとえ話と実際の動作の対応'),
    ('04_設定値一覧', '55項目の既定値とオンライン／バッチ推奨'),
    ('05_通信経路の動作', '通信経路16項目の開始点・効果・理由'),
    ('06_JBossとJavaの動作', 'JBoss／Java20項目の詳細'),
    ('07_Proxyの動作', 'RDS Proxy7項目の詳細'),
    ('08_DBの動作', 'MySQL／Aurora12項目の詳細'),
    ('09_JNDIとバッチ', '同じ資材を異なる実行環境で使う方法'),
    ('10_共有DBの設計', 'SESSION分離・pinning・接続数の設計'),
    ('11_取消と再試行', 'rollback・結果不明・冪等性'),
    ('12_時間予算', '開始点と残時間・動作イメージ'),
    ('13_予算計算', '入力可能な時間・接続予算の計算表'),
    ('14_障害シナリオ', '15ケースの期待動作と合格条件'),
    ('15_設定と確認例', '14個のCLI／SQL／Java等の例'),
    ('16_導入と検証', '試験・段階適用・戻し方'),
    ('17_監視', '層別のメトリクスと読み方'),
    ('18_歴史と背景', '必要になった背景と公式発表の年表'),
    ('19_用語集', '25語をやさしく説明'),
    ('20_出典', f'公式資料{len(SOURCES)}件・確認日・根拠範囲'),
    ('21_確認リスト', '運用前に埋める15項目'),
]

wb = xlsxwriter.Workbook(XLSX, {'strings_to_urls': False, 'strings_to_formulas': False})
wb.set_properties({'title': TITLE, 'subject': SUBTITLE, 'author': '技術設計資料',
                   'comments': '公開公式資料に基づく設計案。実環境への設定変更は未実施。',
                   'created': datetime(2026, 10, 11, 0, 0, 0)})
wb.formats[0].set_font_name('Meiryo UI')
wb.formats[0].set_font_size(10)
wb.formats[0].set_font_color('#222222')
wb.set_calc_mode('auto')

@lru_cache(maxsize=None)
def fmt(kind='body', shade=False):
    base = {'font_name': 'Meiryo UI', 'font_size': 10.5, 'font_color': '#222222',
            'valign': 'top', 'text_wrap': True}
    if kind == 'title':
        base.update(font_size=21, bold=True, bg_color='#252525', font_color='#FFFFFF', valign='vcenter')
    elif kind == 'subtitle':
        base.update(font_size=10, bg_color='#E9E9E9', valign='vcenter')
    elif kind == 'head':
        base.update(bold=True, bg_color='#414141', font_color='#FFFFFF', valign='vcenter', border=1, border_color='#FFFFFF')
    elif kind == 'label':
        base.update(bold=True, bg_color='#E7E7E7', border=1, border_color='#CFCFCF')
    elif kind in ('body','source','link','code','input','number','formula','status'):
        base.update(bg_color=('#F2F2F2' if shade else '#FFFFFF'), bottom=1, bottom_color='#D1D1D1')
        if kind in ('source','link'):
            base.update(underline=1, font_color='#333333')
        if kind == 'code':
            base.update(font_size=10, bg_color='#F3F3F3')
        if kind in ('input','number','formula'):
            base.update(align='right', valign='vcenter', num_format='0.0', font_size=12)
        if kind == 'input':
            base.update(bg_color='#E0E0E0', border=1, border_color='#707070', bold=True)
        if kind == 'formula':
            base.update(bg_color='#F0F0F0', bold=True)
        if kind == 'status':
            base.update(bg_color='#E0E0E0', border=1, border_color='#707070')
    elif kind == 'box':
        base.update(bg_color='#E8E8E8', border=1, border_color='#555555', bold=True, align='center', valign='vcenter', font_size=11)
    elif kind == 'arrow':
        base.update(font_size=17, align='center', valign='vcenter')
    elif kind == 'small':
        base.update(font_size=9, font_color='#555555')
    return wb.add_format(base)

wb.default_url_format = fmt('link')
FONT_FILE = Path('C:/Windows/Fonts/meiryo.ttc')
FONT = ImageFont.truetype(str(FONT_FILE), 14, index=2)

@lru_cache(maxsize=4000)
def char_width(char):
    return FONT.getlength(char)

def lines_needed(value, width, scale=1.0):
    # Conservative character wrapping, including explicit newlines; in pixels at 96 dpi.
    limit = max(20, width * 7 + 5 - 16)
    count = 0
    for line in str(value).split('\n'):
        w = 0
        count += 1
        for char in line:
            cw = char_width(char) * scale
            if w + cw > limit:
                count += 1
                w = 0
            w += cw
    return count

def row_height(values, widths, minimum=30):
    lines = max(lines_needed(v, w, 1.07) for v, w in zip(values, widths))
    result = max(minimum, lines * 15 + 13)
    if result > 405:
        raise ValueError(f'Row exceeds Excel height limit: {result}: {str(values)[:140]}')
    return result

def refs_ids(value):
    return re.findall(r'S\d{2}', value or '')

def write_refs(ws, row, col, refs, shaded=False):
    ids = refs_ids(refs)
    if not ids:
        ws.write_string(row, col, refs or '設計提案', fmt('small'))
        return
    first_row = 6 + list(SOURCE_MAP).index(ids[0])
    display = '\n'.join(' '.join(ids[i:i+2]) for i in range(0,len(ids),2))
    ws.write_url(row, col, f"internal:'20_出典'!A{first_row}", fmt('source', shaded), display)
    ws.write_comment(row, col, '\n\n'.join(f'{i}: {SOURCE_MAP[i][2]}\n{SOURCE_MAP[i][3]}' for i in ids),
                     {'font_name': 'Meiryo UI', 'font_size': 10, 'width': 500, 'height': 180})

def base_sheet(name, title, subtitle, widths, landscape=True, large=False):
    ws = wb.add_worksheet(name)
    ws.hide_gridlines(2)
    ws.set_zoom(80 if sum(widths) > 165 else 90)
    ws.set_tab_color('#707070')
    ws.set_default_row(24)
    for col, width in enumerate(widths):
        ws.set_column(col, col, width, fmt('body'))
    last = len(widths) - 1
    ws.merge_range(0, 0, 0, last, title, fmt('title'))
    ws.set_row(0, 43)
    ws.merge_range(1, 0, 1, last, subtitle, fmt('subtitle'))
    ws.set_row(1, 38)
    if name != '00_読み方':
        ws.write_url(2, 0, "internal:'00_読み方'!A1", fmt('link'), '目次へ')
        if last >= 2:
            ws.merge_range(2, 1, 2, last, '確認日 2026-10-11  |  推奨値は仮定に基づく初期案  |  出典IDはクリック可能', fmt('small'))
    ws.freeze_panes(5, 1 if sum(widths) > 165 else 0)
    ws.repeat_rows(0, 4)
    ws.set_landscape() if landscape else ws.set_portrait()
    ws.set_paper(8 if large else 9)  # A3 or A4
    ws.fit_to_pages(1, 0)
    ws.set_margins(.28, .28, .4, .4)
    ws.set_header('&L&"Meiryo UI,Regular"&8 AWS Timeout Design&C&"Meiryo UI,Regular"&8' + name)
    ws.set_footer('&L&"Meiryo UI,Regular"&8公開資料に基づく設計案 / 実環境未検証&R&"Meiryo UI,Regular"&8&P / &N')
    return ws

def header(ws, labels, row=4):
    for c, label in enumerate(labels):
        ws.write_string(row, c, label, fmt('head'))
    ws.set_row(row, 32)

def table_sheet(name, title, subtitle, labels, rows, widths, source_col=None, large=False):
    ws = base_sheet(name, title, subtitle, widths, large=large)
    header(ws, labels)
    for r, values in enumerate(rows, 5):
        shade = r % 2 == 0
        for c, value in enumerate(values):
            if c == source_col:
                write_refs(ws, r, c, value, shade)
            elif isinstance(value, (int, float)):
                ws.write_number(r, c, value, fmt('number', shade))
            else:
                ws.write_string(r, c, str(value), fmt('body', shade))
        measured=list(values)
        if source_col is not None:
            ids=refs_ids(measured[source_col])
            measured[source_col]='\n'.join(' '.join(ids[i:i+2]) for i in range(0,len(ids),2))
        ws.set_row(r, row_height(measured, widths))
    ws.autofilter(4, 0, len(rows) + 4, len(labels) - 1)
    ws.print_area(0, 0, len(rows) + 4, len(labels) - 1)
    return ws

def narrative(name):
    sec = SECTION_MAP[name]
    return table_sheet(name, sec['title'], '説明は設計提案を含みます。製品の仕様・既定値の根拠は各行の出典を参照してください。',
                       ['論点', '詳しい説明', '根拠'], sec['items'], [24, 102, 14], 2)

def build_index():
    rows = [(name, desc) for name, desc in NAV[1:]]
    ws = base_sheet('00_読み方', TITLE, SUBTITLE + '  |  2026-10-11  |  Meiryo UI・モノトーン', [32, 102])
    header(ws, ['シート（クリックで移動）','内容・使い方'])
    for r,(name,desc) in enumerate(rows,5):
        ws.write_url(r,0,f"internal:'{name}'!A1",fmt('link',r%2==0),name)
        ws.write_string(r,1,desc,fmt('body',r%2==0))
        ws.set_row(r,30)
    r=len(rows)+7
    ws.merge_range(r,0,r,1,'読み順：01→02a→03→04。その後、担当範囲の動作詳細→共有DB→取消→設定例→検証へ進んでください。',fmt('label'))
    ws.set_row(r,47)
    ws.merge_range(r+2,0,r+2,1,'編集できる箇所：13_予算計算の灰色入力セル、21_確認リストの状態欄。計算シートの変更は比較表へ自動反映されません。採用値は表と設定例も合わせて更新してください。',fmt('body'))
    ws.set_row(r+2,65)
    ws.merge_range(r+4,0,r+4,1,'確度の区別：公式既定値 / サービス制約 / 本構成の推奨初期値 / 実機で要確認。8.1資料に数値がない属性は旧版の値を断定せず、その旨を一覧に表示しています。',fmt('body'))
    ws.set_row(r+4,65)
    ws.merge_range(r+6,0,r+6,1,f'実AWS・MySQL・JBossへの接続、設定変更、負荷試験は未実施です。比較表55項目、障害シナリオ15件、設定例14件、公式出典{len(SOURCES)}件を収録。推奨値はAWS等の一律推奨ではありません。',fmt('body'))
    ws.set_row(r+6,65)
    ws.print_area(0,0,r+6,1)

def build_diagram():
    ws=base_sheet('02a_構成図','通信の道と、2種類の時計','オンラインとバッチはDBを共有。HTTP接続とJDBC接続は別物です。',[12]*12)
    ws.freeze_panes(4,0)
    ws.repeat_rows(0,1)
    def box(r,c1,c2,text):
        ws.merge_range(r,c1,r+1,c2,text,fmt('box'))
        ws.set_row(r,29); ws.set_row(r+1,29)
    def arrow(r,c1,c2,text='→'):
        if c1==c2: ws.write(r,c1,text,fmt('arrow'))
        else: ws.merge_range(r,c1,r,c2,text,fmt('arrow'))
        ws.set_row(r,28)
    box(4,0,2,'ブラウザ\n全体35秒')
    arrow(4,3,3)
    box(4,4,7,'API Gateway REST\n統合29秒 / BUFFERED')
    arrow(4,8,8)
    box(4,9,11,'VPC Link V2\nENI / VPC経路')
    arrow(6,9,11,'↓')
    box(7,0,11,'検査の往復：GWLBE → GWLB → Palo Alto → GWLB → GWLBE\nGWLB TCP idle 350秒 / Palo Alto 実効値を確認（global TCP既定3600秒）')
    arrow(9,0,2,'↓')
    box(10,0,2,'ALB\nHTTP idle60秒')
    arrow(10,3,3)
    box(10,4,8,'ECS Fargate / JBoss EAP 8.1\nOpenJDK21 / JNDI DataSource')
    arrow(10,9,11,'→ JDBC')
    arrow(12,9,11,'↓')
    box(13,0,5,'EC2 Javaバッチ（同じ業務資材）\nbatch用DataSource factory / policy')
    arrow(13,6,7)
    box(13,8,11,'RDS Proxy（基本案は共有）\nidle30分 / borrow2秒')
    arrow(15,8,11,'↓ JDBC')
    box(16,0,11,'共有DB：Aurora Serverless v2 / Aurora MySQL 8.4.7\nwait_timeout 8時間を基準に維持 / SQLとlockの期限は用途別SESSION')
    ws.merge_range(19,0,19,11,'使っていないDB接続を片付ける時計',fmt('head'));ws.set_row(19,28)
    ws.merge_range(20,0,21,11,'アプリpool 5分（回収目安5～7.5分） < Proxy idle 30分 < DB idle 8時間\nclient = ECS / EC2 のDB client。ブラウザの35秒やsocketTimeoutをこの式へ入れません。',fmt('box'))
    ws.set_row(20,30);ws.set_row(21,30)
    ws.merge_range(23,0,23,11,'処理を打ち切り、説明を返す時計（開始点はそれぞれ違う）',fmt('head'));ws.set_row(23,28)
    ws.merge_range(24,0,25,11,'読取SQL 8秒 → query取消 12秒 → socket無応答 15秒 → TX 20秒 → app 25秒 → API 29秒 → browser 35秒\nquery12秒はborrow2秒＋DB8秒＋余白2秒。残予算の伝播と取消完了の検証が必要です。',fmt('box'))
    ws.set_row(24,34);ws.set_row(25,34)
    ws.merge_range(27,0,28,11,'構成図は概念図です。検査経路の往復・AZ・ルートは実環境で確認。提示されたEC2/ECS→RDS ProxyのDB通信にはGWLB/Palo Altoを追加していません。\n根拠：S01 / S06 / S09 / S12 / S15 / S22 / S28。数値は本構成の初期案。',fmt('small'))
    ws.set_row(27,25);ws.set_row(28,25)
    ws.set_paper(8)
    ws.fit_to_pages(1,1)
    ws.print_area(0,0,28,11)

def build_parameters():
    widths=[7,36,18,31,28,30,32,13]
    rows=[(p['id'],p['key'],p['kind'],p['default'],p['online'],p['batch'],p['scope'],p['refs']) for p in PARAMS]
    ws=table_sheet('04_設定値一覧','既定値と推奨初期値：55項目','推奨は未確定要件に対する初期案。0の意味・単位・設定範囲を必ず確認。IDから詳細へ移動できます。',
                   ['ID','設定名','時計の種類','公式既定／確認状況','オンライン推奨','バッチ推奨','設定単位・場所','根拠'],rows,widths,7,True)
    for r,p in enumerate(PARAMS,5):
        group=[x for x in PARAMS if x['group']==p['group']]
        target_row=6+group.index(p)
        ws.write_url(r,0,f"internal:'{GROUP_SHEETS[p['group']]}'!A{target_row}",fmt('link',r%2==0),p['id'])
    for group,name in GROUP_SHEETS.items():
        rows=[(p['id']+'\n'+p['key'],p['start'],p['effect'],p['reason'],p['caveat'],p['refs']) for p in PARAMS if p['group']==group]
        table_sheet(name,group+'：タイムアウトの動作と採用理由','比較値は04_設定値一覧を参照。ここでは開始点、止まる対象、誤解しやすい点を説明します。',
                    ['ID / 設定名','いつ計り始めるか','期限になると何が起こるか','本案の理由','制約・落とし穴','根拠'],rows,[35,29,37,34,56,13],5,True)

def build_calculator():
    ws=base_sheet('13_予算計算','入力して確かめる：時間予算と接続予算','灰色の数値セルが入力欄です。計算結果は一覧・設定例へ自動反映されません。',[44,16,15,87])
    header(ws,['項目','値','単位','意味 / 制約'])
    for r,(label,val,note) in enumerate(BUDGET,5):
        ws.write(r,0,label,fmt('body'));ws.write_number(r,1,val,fmt('input'));ws.write(r,2,'秒',fmt('body'));ws.write(r,3,note,fmt('body'));ws.set_row(r,44)
        ws.data_validation(r,1,r,1,{'validate':'decimal','criteria':'between','minimum':0,'maximum':3600})
    def calc_row(r,label,value,unit,note,formula=None,percent=False):
        ws.write(r,0,label,fmt('label'))
        if formula:
            ws.write_formula(r,1,formula,fmt('formula'),value)
        else:
            f=fmt('input')
            if percent:
                f=wb.add_format({'font_name':'Meiryo UI','font_size':12,'bold':True,'font_color':'#222222','bg_color':'#E0E0E0','num_format':'0%','border':1,'border_color':'#707070','align':'right','valign':'vcenter','text_wrap':True})
            ws.write_number(r,1,value,f)
            ws.data_validation(r,1,r,1,{'validate':'decimal','criteria':'between','minimum':0,'maximum':1 if percent else 1000000})
        ws.write(r,2,unit,fmt('body'));ws.write(r,3,note,fmt('body'));ws.set_row(r,48)
    calc_row(12,'配分合計',25,'秒','排他的に計測した要素の合計。重複計上を避ける','=SUM(B6:B12)')
    calc_row(14,'アプリ要求deadline',25,'秒','入口から。実装で残時間を管理する')
    calc_row(15,'API Gateway統合期限',29,'秒','BUFFERED REST。緩和時はAPI種別とquotaを再確認')
    calc_row(16,'ブラウザ要求期限',35,'秒','入口までのネットワークと応答受信の余裕を取る')
    calc_row(18,'Gatewayとappの差',4,'秒','開始点が異なるため、保証値ではなく設計余白','=B16-B15')
    calc_row(19,'browserとGatewayの差',6,'秒','ブラウザ側の通信・処理を含め実測する','=B17-B16')
    ws.write(21,0,'時間予算の整合性',fmt('label'))
    ws.write_formula(21,1,'=IF(AND(B13<=B15,B15<B16,B16<B17),"予算内","要再設計")',fmt('formula'),'予算内')
    ws.merge_range(21,2,21,3,'判定は算術のみ。thread停止やDB rollback完了を保証する試験ではありません。',fmt('body'));ws.set_row(21,48)
    header(ws,['idle回収の関係','値','単位','意味 / 制約'],24)
    calc_row(25,'JBoss pool idle設定',5,'分','最小idleのpoolも5分とする計算例')
    calc_row(26,'IdleRemover走査周期の目安',2.5,'分','別poolに短いidle値があればその半分で計算する','=B26/2')
    calc_row(27,'pool回収までの目安上限',450,'秒','実行遅延は別途。借用中接続はidle回収対象でない','=(B26+B27)*60')
    calc_row(28,'RDS Proxy IdleClientTimeout',1800,'秒','client接続idle。backend接続と同じ時計ではない')
    calc_row(29,'DB wait_timeout',28800,'秒','MySQL既定を基準。実際のSESSION値で確認')
    ws.write(30,0,'idle設定の整合性',fmt('label'))
    ws.write_formula(30,1,'=IF(AND(B28<B29,B29<B30),"余白あり","要再設計")',fmt('formula'),'余白あり')
    ws.merge_range(30,2,30,3,'同じ無通信区間に他のFW/NATがあれば、そのidleも別に評価します。',fmt('body'));ws.set_row(30,48)
    header(ws,['接続数の仮入力','値','単位','意味 / 制約'],33)
    calc_row(34,'DB max_connections',1000,'本','例示値。Auroraから実値を取得する')
    calc_row(35,'共有proxy MaxConnectionsPercent',0.70,'比率','70%は本資料の仮例。秒数ではない',percent=True)
    calc_row(36,'割合からの理論枠',700,'本','サービス予約枠等により実効上限とは異なる','=B35*B36')
    calc_row(37,'MaxDatabaseConnectionsAllowed',650,'本','観測値を入力する欄。650本は実測ではなく例示値')
    calc_row(38,'ピークのbackend同時利用',450,'本','online＋batchの観測値。pinningの専有も含め評価')
    calc_row(39,'ピークに30%余裕を加えた目安',585,'本','DBの30%を必ず空けるという意味とは別','=B39*1.3')
    ws.write(40,0,'接続予算の整合性',fmt('label'))
    ws.write_formula(40,1,'=IF(B40<=B38,"枠内","要再設計")',fmt('formula'),'枠内')
    ws.merge_range(40,2,40,3,'複数proxyでは全proxyと管理/直接接続の合計も評価。CPU/I/Oの容量保証は別。',fmt('body'));ws.set_row(40,48)
    ws.print_area(0,0,40,3)
    ws.set_h_pagebreaks([24,33])

def build_examples():
    ws=base_sheet('15_設定と確認例','確認コマンドと設定・実装例','すべてレビュー用の例です。実環境で実行していません。読取例と変更例を区別してください。',[8,38,38,38])
    ws.freeze_panes(4,0)
    ws.repeat_rows(0,1)
    r=4
    breaks=[]
    for item in EXAMPLES:
        breaks.append(r)
        ws.merge_range(r,0,r,3,item['title']+'  ['+item['language']+']',fmt('head'));ws.set_row(r,34);r+=1
        text=item['note']+'  根拠: '+item['refs']
        ws.merge_range(r,0,r,3,text,fmt('body'));ws.set_row(r,row_height([text],[122],40));r+=1
        for n,line in enumerate(item['code'].splitlines(),1):
            ws.write_number(r,0,n,fmt('small'))
            ws.merge_range(r,1,r,3,line if line else ' ',fmt('code'))
            ws.set_row(r,max(21,lines_needed(line,114,1.06)*14+8));r+=1
        r+=1
    ws.set_h_pagebreaks(breaks[1:])
    ws.print_area(0,0,r-1,3)

def build_sources():
    ws=table_sheet('20_出典','公式資料と根拠の範囲','確認日：2026-10-11。動的なlatest資料は将来変わり得ます。EAP 6.4資料は歴史的参考として明示。',
                   ['ID','発行元','資料タイトル（リンク）','確認した仕様 / 利用範囲','URL','確認日'],
                   [(sid,org,title,scope,url,DATE) for sid,org,title,url,scope in SOURCES],
                   [7,19,47,51,66,14],large=True)
    for r,(sid,org,title,url,scope) in enumerate(SOURCES,5):
        ws.write_url(r,2,url,fmt('link',r%2==0),title)
        ws.write_url(r,4,url,fmt('link',r%2==0),url)

def build_checklist():
    ws=table_sheet('21_確認リスト','導入前チェックリスト','状態は実環境の確認結果に合わせて更新してください。初期状態は未確認／未実施です。',
                   ['ID','分類','確認すること','担当','完了の証拠','状態'],CHECKS,[7,14,64,23,62,15])
    for r,item in enumerate(CHECKS,5):
        ws.write(r,5,item[5],fmt('status'))
    ws.data_validation(5,5,len(CHECKS)+4,5,{'validate':'list','source':['未確認','未実施','未確定','確認中','完了','対象外']})

def build_workbook():
    build_index()
    narrative('01_結論と前提');narrative('02_構成と担当');build_diagram();narrative('03_時計の原理')
    build_parameters()
    for name in ['09_JNDIとバッチ','10_共有DBの設計','11_取消と再試行','12_時間予算']:
        narrative(name)
    build_calculator()
    table_sheet('14_障害シナリオ','障害時の動作：15ケース','推奨値は目標の発火順序。取消・rollbackの実時間は検証し、例外発生だけで合格としません。',
                ['ID','場面','発生条件','最初に見る時計','対応','観測するもの','合格条件'],SCENARIOS,[7,20,32,37,42,40,40],large=True)
    build_examples();narrative('16_導入と検証')
    table_sheet('17_監視','どこで待っているかを観測する','メトリクスの名前だけで原因を決めず、時刻・要求ID・mode・DB側状態を突き合わせます。',
                ['層','確認する情報','目標 / 判断の仕方','誤読を避ける注意','根拠'],MONITORING,[23,69,56,54,14],4,True)
    table_sheet('18_歴史と背景','登場の歴史と、必要になった理由','日付は対応する公式発表によります。初期の一般論は技術の背景説明で、製品の初出年を断定していません。',
                ['時期','背景 / 困りごと','登場・変化','やさしいたとえ','根拠'],HISTORY,[22,47,56,45,16],4)
    table_sheet('19_用語集','用語をやさしく説明する','たとえ話は理解を助けるもので、製品動作の厳密な仕様は本文と出典を参照してください。',
                ['用語','意味','たとえ'],GLOSSARY,[31,66,57])
    build_sources();build_checklist()
    wb.worksheets()[0].activate()
    wb.worksheets()[0].set_first_sheet()
    wb.close()

def cite(refs):
    ids=refs_ids(refs)
    if not ids:return '' if not refs else refs
    return ' / '.join(f'[{sid} {SOURCE_MAP[sid][1]}]({SOURCE_MAP[sid][3]})' for sid in ids)

def escape_cell(value):
    return str(value).replace('|','\\|').replace('\n','<br>')

def md_table(labels,rows):
    lines=['| '+' | '.join(labels)+' |','| '+' | '.join(['---']*len(labels))+' |']
    lines.extend('| '+' | '.join(escape_cell(x) for x in row)+' |' for row in rows)
    return '\n'.join(lines)

def build_markdown():
    lines=[f'# {TITLE}', '',SUBTITLE,'',f'確認日：**{DATE}（JST）**。要件未定のため、本構成向けの推奨初期値を仮定つきで示します。',
           '',f'対応Excel：[{XLSX.name}]({XLSX.name})。23シート、比較55項目、障害15ケース、設定例14件、公式出典{len(SOURCES)}件。',
           '','公式既定・製品制約と、筆者が組み立てた設計案は区別しています。AWS・JBoss・DBへの設定変更、実システムの負荷試験は未実施です。',
           '','## 読み順','', '結論と前提 → 構成図 → 時計の原理 → 比較表 → 担当範囲の動作詳細 → JNDI/共有DB → 取消 → 時間予算 → 設定例 → 検証、の順がおすすめです。',
           '', '**先に押さえる2つの式**',
           '', '- 接続のidle回収：アプリpool **5分（回収目安5～7.5分） < Proxy 30分 < DB 8時間**。',
           '- 処理の期限：onlineは**DB読取8秒 → query12秒 → socket無応答15秒 → TX20秒 → app25秒 → API29秒 → browser35秒**。query12秒はborrow2秒＋DB8秒＋余白2秒を考慮。残時間の伝播も必要です。',
           '', f'AWSの `client timeout < proxy timeout < database timeout` は、ここではDB clientのidle回収の文脈で読みます。{cite("S01")}', '']
    def append_section(name):
        sec=SECTION_MAP[name]
        lines.extend(['## '+sec['title'],''])
        for label,text,refs in sec['items']:
            lines.extend(['### '+label,'',text+((' '+cite(refs)) if refs else ''),''])
    append_section('01_結論と前提');append_section('02_構成と担当')
    lines.extend(['### 構成図','', '```mermaid', 'flowchart TD',
                  '    B["ブラウザ：要求35秒"] --> A["API Gateway REST：統合29秒"]',
                  '    A --> V["VPC Link V2：ENI・VPCルート"]',
                  '    V --> I["検査往復：GWLBE → GWLB → Palo Alto → GWLB → GWLBE"]',
                  '    I --> L["ALB：HTTP idle60秒"]',
                  '    L --> E["ECS Fargate：JBoss EAP8.1 / OpenJDK21 / JNDI DataSource"]',
                  '    E --> P["RDS Proxy：idle1800秒 / borrow2秒（共有の基本案）"]',
                  '    C["EC2 Javaバッチ：共通資材＋batch設定"] --> P',
                  '    P --> D["Aurora Serverless v2：MySQL8.4.7互換 / 共有DB"]',
                  '```','', '図のHTTP通信とDB通信は別の接続です。検査経路は概念図で、実際の往復ルート・AZ・SG/NACLは別途確認します。', ''])
    append_section('03_時計の原理')
    lines.extend(['## 既定値と推奨初期値の一覧','', '単位を省略しません。「0」は設定によって意味が異なります。MySQL欄の既定はCommunity 8.4の仕様値であり、Auroraのparameter groupや実効SESSION値を未確認のまま断定するものではありません。',''])
    for group in GROUP_SHEETS:
        lines.extend(['### '+group,'',md_table(['ID','設定名 / 種類','公式既定・確認状況','オンライン推奨','バッチ推奨','設定単位・場所','根拠'],
             [(p['id'],p['key']+' / '+p['kind'],p['default'],p['online'],p['batch'],p['scope'],cite(p['refs'])) for p in PARAMS if p['group']==group]),''])
    lines.extend(['## 55項目の動作原理・採用理由・落とし穴',''])
    for p in PARAMS:
        lines.extend([f'### {p["id"]}　{p["key"]}','',
                      '- **開始点**：'+p['start']+'。',
                      '- **期限時の動作**：'+p['effect']+'。',
                      '- **推奨理由**：'+p['reason']+'。',
                      '- **制約・注意**：'+p['caveat']+'。 '+cite(p['refs']),''])
    for name in ['09_JNDIとバッチ','10_共有DBの設計','11_取消と再試行','12_時間予算']:
        append_section(name)
    lines.extend(['### 25秒の予算配分例','',md_table(['区間','予算（秒）','備考'],BUDGET),'',
                  '**合計25秒**。Excelの「13_予算計算」で入力値を変更して確認できます。計算結果は設定一覧や例へ自動反映されません。',
                  '', '### 具体的な初期値の比較','',
                  md_table(['時計','オンライン','バッチ'],[
                      ('DB SELECT','8秒','45秒'),('JDBC query','12秒＋残予算で短縮','60秒＋残予算で短縮'),
                      ('JDBC socket無応答','15秒','90秒'),('TX','JTAで20秒を個別設定','共通層で120秒の予算'),
                      ('処理全体','要求25秒','1チャンク180秒、全jobは別'),('pool idle','5分＋回収走査','poolなしなら処理単位でclose'),
                      ('Proxy idle','30分','共有proxyは同じ30分'),('DB idle','8時間を基準に維持','同左')]),'',
                  '### 接続予算の計算例','', 'DB上限1000本、proxy割合70%なら理論枠700本。実効のMaxDatabaseConnectionsAllowedを仮に650本、需要ピーク450本とすると、30%の余裕込み585本が枠内になります。いずれも計算例で実測値ではありません。複数proxyは枠の合計と、管理用・直接接続の余裕を確認します。 '+cite('S02 S03'),''])
    lines.extend(['## 障害時の動作イメージと試験','',md_table(['ID','場面','条件','時計','対応','観測','合格条件'],SCENARIOS),''])
    lines.extend(['## 確認コマンドと設定・実装例','', '以下はレビュー用で未実行です。プレースホルダーを実環境の値へ置換してください。読取コマンドと変更例を混同せず、既存のTLS・認証・URL・pool設定を保持します。',''])
    for item in EXAMPLES:
        lines.extend(['### '+item['title'],'',item['note']+' '+cite(item['refs']),'','```'+item['language'],item['code'],'```',''])
    append_section('16_導入と検証')
    lines.extend(['## 監視の設計','',md_table(['層','確認情報','判断','注意','根拠'],[(*r[:-1],cite(r[-1])) for r in MONITORING]),'',
                  '## 登場の歴史と背景','',md_table(['時期','背景','変化','やさしいたとえ','根拠'],[(*r[:-1],cite(r[-1])) for r in HISTORY]),'',
                  '## 用語集','',md_table(['用語','意味','たとえ'],GLOSSARY),'',
                  '## 導入前チェックリスト','',md_table(['ID','分類','確認事項','担当','証拠','状態'],CHECKS),'',
                  '## 出典一覧','', '確認日はいずれも2026-10-11。動的なlatest資料は更新されるため、導入前に対象版と実効設定で読み直してください。推奨数値そのものは本構成の設計案です。',''])
    for sid,org,title,url,scope in SOURCES:
        lines.extend([f'- **{sid}** {org} — [{title}]({url})：{scope}。'])
    lines.extend(['','## 本資料に残る確認事項','',
                  '業務SLO、batch完了時刻、リージョン、API endpoint種別、ドライバー/PAN-OS/EAP patch、非XA/XA、pool製品、実効parameter group、SQL別p99、最大同時数、Proxyが共通か別かは未確定または未確認です。推奨は検証開始点として使い、query取消・結果不明・共有DB負荷の試験結果で確定してください。',''])
    MD.write_text('\n'.join(lines),encoding='utf-8',newline='\n')

if __name__ == '__main__':
    assert len(PARAMS)==55 and len(SOURCES)==57 and len(SCENARIOS)==15 and len(EXAMPLES)==14
    build_workbook()
    build_markdown()
    print(json.dumps({'xlsx':str(XLSX),'markdown':str(MD),'sheets':len(NAV),'parameters':len(PARAMS),
                      'sources':len(SOURCES),'scenarios':len(SCENARIOS),'examples':len(EXAMPLES)},ensure_ascii=True))
