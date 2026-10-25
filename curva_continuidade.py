"""Continuação ilustrativa da série de apuração até o resultado FINAL do modelo.

Não estima resultado eleitoral: o alvo final vem exclusivamente de projetar_locais.
A inclinação no ponto de junção é estimada das parciais nacionais recentes.
"""
from __future__ import annotations
from datetime import datetime
from math import ceil, exp, isfinite


def limpar_pontos(pontos):
    """Preserva a ordem temporal, ignora retrocessos e colapsa x repetidos.

    Cada entrada é (percentual_de_votos_apurados, percentual_lula, capturado_iso).
    O eixo x deve ter o MESMO denominador final estimado para todas as parciais.
    """
    validos = []
    for ponto in pontos:
        if len(ponto) < 2:
            continue
        try:
            x, y = float(ponto[0]), float(ponto[1])
        except (ValueError, TypeError):
            continue
        if not (isfinite(x) and isfinite(y) and 0 <= x <= 100 and 0 <= y <= 100):
            continue
        momento = ponto[2] if len(ponto) >= 3 else None
        atual = (x, y, momento)
        if validos and x < validos[-1][0] - 1e-8:
            continue
        if validos and abs(x - validos[-1][0]) < 1e-8:
            validos[-1] = atual
        else:
            validos.append(atual)
    return validos


def _minutos_entre(mais_recente, anterior):
    if not mais_recente or not anterior:
        return None
    try:
        fim, inicio = datetime.fromisoformat(str(mais_recente)), datetime.fromisoformat(str(anterior))
        return max(0., (fim - inicio).total_seconds() / 60.)
    except (ValueError, TypeError):
        return None


def inclinacao_recente(pontos, inclinacao_neutra=0.):
    """Regressão local ponderada pelos últimos 8 p.p. e pela recência temporal.

    Inclinação em p.p. de Lula para cada 1 p.p. adicional de votos apurados.
    Com histórico muito curto, evita extrapolar ruído: usa a secante até o alvo.
    """
    if len(pontos) < 2:
        return float(inclinacao_neutra)
    x_fim, _, t_fim = pontos[-1]
    janela = [p for p in pontos if p[0] >= x_fim - 8.][-20:]
    if len(janela) < 2 or x_fim - janela[0][0] < 0.6:
        return float(inclinacao_neutra)
    pesos = []
    for x, _, t in janela:
        w = exp(-max(0., x_fim - x) / 5.)
        minutos = _minutos_entre(t_fim, t)
        if minutos is not None:
            w *= exp(-min(minutos, 240.) / 40.)
        pesos.append(w)
    soma_pesos = sum(pesos)
    centro_x = sum(w*p[0] for w,p in zip(pesos,janela)) / soma_pesos
    centro_y = sum(w*p[1] for w,p in zip(pesos,janela)) / soma_pesos
    denom = sum(w*(p[0]-centro_x)**2 for w,p in zip(pesos,janela))
    if denom < 0.03:
        return float(inclinacao_neutra)
    return sum(w*(p[0]-centro_x)*(p[1]-centro_y) for w,p in zip(pesos,janela)) / denom


def construir_continuacao(pontos, lula_final, passos_por_pp=2):
    """Gera trajetória suave de (x_atual, parcial) até (100, alvo_do_modelo).

    Sem salto no ponto de junção e com derivada inicial correspondente à
    tendência recente (ponderada pelo tempo). Curvatura decai suavemente para
    atingir exatamente o resultado final. Flávio é sempre 100 menos Lula.

    Retorna pares (x, Lula) incluindo o ponto de junção; vazio se não há
    projeção válida, apuração real ou votos remanescentes.
    """
    serie = limpar_pontos(pontos)
    if not serie:
        return []
    try:
        alvo = float(lula_final)
    except (ValueError, TypeError):
        return []
    if not isfinite(alvo) or not 0 <= alvo <= 100:
        return []
    x0, y0, _ = serie[-1]
    restante = 100. - x0
    if x0 <= 0 or restante <= 1e-8:
        return []
    diferenca = alvo - y0
    secante = diferenca / restante
    tendencia = inclinacao_recente(serie, secante)
    # Reduz extrapolações exageradas de amostras iniciais/instáveis.
    max_inclinacao = min(.40, max(.08, 4.*abs(secante)))
    tendencia = max(-max_inclinacao, min(max_inclinacao, tendencia))
    n = max(2, min(250, ceil(restante * passos_por_pp)))
    resultado = []
    for i in range(n + 1):
        t = i / n
        x = x0 + restante*t
        # A derivada em t=0 é tendencia*restante.
        # Em t=1 o valor é exatamente "alvo", sem extrapolação posterior.
        ajuste = (tendencia*restante - diferenca)*t*(1-t)**2
        y = y0 + diferenca*t + ajuste
        resultado.append((x, max(0., min(100., y))))
    resultado[0] = (x0, y0)
    resultado[-1] = (100., alvo)
    return resultado
