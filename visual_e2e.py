"""E2E em Chromium real, desktop e viewport de smartphone.

Rodar:
  pip install playwright && python -m playwright install chromium
  streamlit run app.py --server.headless=true --server.port=8501
  python visual_e2e.py
Grava PNGs e um relatório JSON, publicados como artifacts do CI.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

URL='http://127.0.0.1:8501'
OUT=Path('visual-auditoria')


def testar(p,rotulo,viewport):
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    context=browser.new_context(viewport=viewport,device_scale_factor=1,
                                is_mobile=rotulo=='mobile',has_touch=rotulo=='mobile')
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    resp=page.goto(URL,wait_until='domcontentloaded',timeout=45000)
    if not resp or resp.status>=400:
        raise AssertionError(f'{rotulo}: app HTTP {resp.status if resp else "sem resposta"}')
    page.get_by_text('Apuração & projeção presidencial',exact=False).wait_for(timeout=45000)
    page.get_by_text('MODO DEMONSTRAÇÃO',exact=False).wait_for(timeout=45000)
    OUT.mkdir(exist_ok=True)
    paginas=[]
    for nome,aba,alvo in (
        ('painel',re.compile('Painel'),'Apuração & projeção presidencial'),
        ('zonas',re.compile('Zonas'),'Apuração e projeção por zona eleitoral'),
        ('historicos',re.compile('Históricos'),'Dados históricos oficiais')
    ):
        page.get_by_role('tab',name=aba).click(timeout=20000)
        page.get_by_text(alvo,exact=False).first.wait_for(timeout=30000)
        path=OUT/f'{rotulo}_{nome}.png'
        page.screenshot(path=str(path),full_page=True,
                        animations='disabled',timeout=45000)
        dimensoes=page.evaluate('''() => ({
           viewport: document.documentElement.clientWidth,
           scroll: document.documentElement.scrollWidth,
           body: document.body.scrollWidth
        })''')
        # Um scrollbar nativo pode adicionar alguns px, mas não rolagem
        # lateral estrutural de 25px+ no telefone.
        if dimensoes['scroll']-dimensoes['viewport']>24:
            raise AssertionError(
                f'{rotulo}/{nome}: overflow horizontal {dimensoes}')
        paginas.append({'aba':nome,'png':str(path),
                        'largura':dimensoes})
    if errors:
        raise AssertionError(f'{rotulo}: erros de JavaScript: {errors[:4]}')
    context.close()
    browser.close()
    return paginas


def main():
    with sync_playwright() as p:
        results={
          'desktop':testar(p,'desktop',{'width':1440,'height':900}),
          'mobile':testar(p,'mobile',{'width':390,'height':844}),
          'nota':'Capturas em Chromium headless CI; revisão humana do aparelho real ainda recomendável'
        }
    (OUT/'relatorio.json').write_text(
        json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
