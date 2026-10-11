"""Open the generated workbook in a separate hidden Excel instance and export review PDFs."""
import json
from pathlib import Path
import win32com.client
import pythoncom

ROOT=Path(__file__).resolve().parents[1]
XLSX=ROOT/'output'/'AWS_Timeout_Design_2026-10-11.xlsx'
OUT=ROOT/'validation'
OUT.mkdir(exist_ok=True)

def main():
    pythoncom.CoInitialize()
    app=None
    book=None
    result={}
    try:
        app=win32com.client.DispatchEx('Excel.Application')
        app.Visible=False
        app.DisplayAlerts=False
        app.AskToUpdateLinks=False
        app.AutomationSecurity=3
        book=app.Workbooks.Open(str(XLSX),UpdateLinks=0,ReadOnly=True)
        app.CalculateFull()
        result['excel_version']=app.Version
        result['sheets']=book.Worksheets.Count
        calc=book.Worksheets('13_予算計算')
        result['calculated']={cell:calc.Range(cell).Value for cell in ['B13','B19','B20','B22','B27','B28','B31','B37','B40','B41']}
        expected={'B13':25,'B19':4,'B20':6,'B22':'予算内','B27':2.5,'B28':450,'B31':'余白あり','B37':700,'B40':585,'B41':'枠内'}
        if result['calculated'] != expected:
            raise ValueError('Excel recalculation mismatch: '+str(result['calculated']))
        for name in ['01_結論と前提','02a_構成図','04_設定値一覧','05_通信経路の動作','13_予算計算','15_設定と確認例','20_出典']:
            path=OUT/(name+'.pdf')
            book.Worksheets(name).ExportAsFixedFormat(0,str(path))
            print(json.dumps({'exported':name,'bytes':path.stat().st_size},ensure_ascii=True),flush=True)
        result['status']='PASS'
    except Exception as exc:
        result['status']='FAIL'
        result['error']=str(exc)
        raise
    finally:
        if book is not None:book.Close(SaveChanges=False)
        if app is not None:app.Quit()
        pythoncom.CoUninitialize()
        (OUT/'excel_render.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
