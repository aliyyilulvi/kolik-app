# -*- coding: utf-8 -*-
"""
analyzer.py
-----------
Kolik'in istatistiksel analiz motoru.

YÖNTEM: Poisson gol dağılımı modeli.
Futbol analitiğinde yaygın kullanılan, her takımın belirli bir maçta
belirli sayıda gol atma olasılığının Poisson dağılımıyla makul şekilde
modellenebildiği varsayımına dayanır (Maher, 1982 ve sonrası literatür).

ÖNEMLİ ETİK/METODOLOJİK NOT:
Bu motor "kesin sonuç" ya da "garanti" üretmez. Ürettiği tüm yüzdeler,
geçmiş verilere dayalı İSTATİSTİKSEL OLASILIKLARDIR. Futbol doğası gereği
yüksek varyanslı bir spordur; hiçbir model %100 (hatta güvenilir şekilde
%80+) isabet garantisi veremez. UI katmanı bu yüzdeleri her zaman
"olasılık" ifadesiyle ve belirsizlik notuyla birlikte göstermelidir.

NOT (v1.1): Bu modül artık NumPy KULLANMIYOR. Android/Buildozer
derlemesinde NumPy'ın cross-compile edilmesi sık sık başarısız oluyor
(özellikle yeni Python sürümlerinde kaldırılan 'cgi' modülüne bağımlı
eski Cython/Tempita bileşenleri yüzünden). Matris işlemleri saf Python
listeleriyle (list of lists) yeniden yazıldı; sonuçlar birebir aynıdır.
"""

import math
from typing import Dict, List, Tuple

from models import Fixture, AnalysisResult

MAX_GOALS = 6           # Skor matrisinde hesaplanacak maksimum gol sayısı
LEAGUE_AVG_GOALS = 1.35  # Basit lig ortalaması varsayımı (gerçek kullanımda ligden hesaplanmalı)
FIRST_HALF_GOAL_RATIO = 0.45  # Maçlarda gollerin istatistiksel olarak ~%45'i ilk yarıda atılır

Matrix = List[List[float]]  # matrix[i][j] = P(ev_sahibi=i gol, deplasman=j gol)


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) burada X ~ Poisson(lam). Harici kütüphane bağımlılığı yok."""
    if lam <= 0:
        lam = 0.01
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _market_value_factor(home_value: float, away_value: float) -> Tuple[float, float]:
    """
    Kadro piyasa değeri oranını küçük bir çarpan olarak döndürür.
    Aşırı etkiyi önlemek için logaritmik ölçek ve dar bir aralığa (0.92-1.08) sıkıştırılmıştır.
    Değer verisi yoksa (0.0) nötr (1.0, 1.0) döner.
    """
    if home_value <= 0 or away_value <= 0:
        return 1.0, 1.0
    ratio = math.log((home_value + 1) / (away_value + 1))
    clipped = max(-1.0, min(1.0, ratio / 5))
    return 1.0 + clipped * 0.08, 1.0 - clipped * 0.08


def compute_expected_goals(fixture: Fixture) -> Tuple[float, float]:
    """
    Ev sahibi ve deplasman takımı için beklenen gol sayılarını (lambda) hesaplar.
    Girdiler: son 5 genel form, ev/deplasmana özel son 3 maç, kadro değeri, hava durumu.
    """
    hs, aws = fixture.home_stats, fixture.away_stats

    home_attack = hs.avg_goals_for() / LEAGUE_AVG_GOALS
    home_defense = hs.avg_goals_against() / LEAGUE_AVG_GOALS
    away_attack = aws.avg_goals_for() / LEAGUE_AVG_GOALS
    away_defense = aws.avg_goals_against() / LEAGUE_AVG_GOALS

    if hs.last3_home_or_away:
        home_specific_attack = hs.avg_goals_for(hs.last3_home_or_away) / LEAGUE_AVG_GOALS
        home_attack = 0.6 * home_attack + 0.4 * home_specific_attack
    if aws.last3_home_or_away:
        away_specific_attack = aws.avg_goals_for(aws.last3_home_or_away) / LEAGUE_AVG_GOALS
        away_attack = 0.6 * away_attack + 0.4 * away_specific_attack

    home_form_mult = 0.9 + hs.form_score() * 0.2
    away_form_mult = 0.9 + aws.form_score() * 0.2

    hv_mult, av_mult = _market_value_factor(hs.squad_market_value_eur, aws.squad_market_value_eur)

    HOME_ADVANTAGE = 1.12

    lambda_home = LEAGUE_AVG_GOALS * home_attack * away_defense * home_form_mult * hv_mult * HOME_ADVANTAGE
    lambda_away = LEAGUE_AVG_GOALS * away_attack * home_defense * away_form_mult * av_mult

    if fixture.weather:
        rf = fixture.weather.rain_factor
        lambda_home *= rf
        lambda_away *= rf

    lambda_home = max(0.3, min(4.0, lambda_home))
    lambda_away = max(0.3, min(4.0, lambda_away))

    return lambda_home, lambda_away


def build_score_matrix(lambda_home: float, lambda_away: float) -> Matrix:
    """(MAX_GOALS+1) x (MAX_GOALS+1) boyutunda skor olasılık matrisi üretir (saf Python)."""
    home_probs = [_poisson_pmf(i, lambda_home) for i in range(MAX_GOALS + 1)]
    away_probs = [_poisson_pmf(j, lambda_away) for j in range(MAX_GOALS + 1)]

    matrix = [[hp * ap for ap in away_probs] for hp in home_probs]

    total = sum(sum(row) for row in matrix)
    if total > 0:
        matrix = [[cell / total for cell in row] for row in matrix]
    return matrix


def _match_result_probs(matrix: Matrix) -> Dict[str, float]:
    n = len(matrix)
    p_home = sum(matrix[i][j] for i in range(n) for j in range(n) if i > j)
    p_draw = sum(matrix[i][i] for i in range(n))
    p_away = sum(matrix[i][j] for i in range(n) for j in range(n) if j > i)
    return {"MS1": p_home, "MSX": p_draw, "MS2": p_away}


def _btts_probs(matrix: Matrix) -> Dict[str, float]:
    p_btts_yes = sum(matrix[i][j] for i in range(1, len(matrix)) for j in range(1, len(matrix[0])))
    return {"KG_VAR": p_btts_yes, "KG_YOK": 1 - p_btts_yes}


def _over_under_probs(matrix: Matrix, line: float) -> Dict[str, float]:
    n = len(matrix)
    over = sum(matrix[i][j] for i in range(n) for j in range(n) if (i + j) > line)
    under = 1 - over
    return {f"UST_{line}": over, f"ALT_{line}": under}


def _row_sums(matrix: Matrix) -> List[float]:
    """Her satırın (ev sahibi gol sayısının) marjinal olasılık dağılımı."""
    return [sum(row) for row in matrix]


def _col_sums(matrix: Matrix) -> List[float]:
    """Her sütunun (deplasman gol sayısının) marjinal olasılık dağılımı."""
    n_cols = len(matrix[0]) if matrix else 0
    return [sum(row[j] for row in matrix) for j in range(n_cols)]


def _team_goals_over_under(probs_1d: List[float], line: float) -> Dict[str, float]:
    over = sum(p for k, p in enumerate(probs_1d) if k > line)
    return {"UST": over, "ALT": 1 - over}


def _half_matrices(lambda_home: float, lambda_away: float) -> Tuple[Matrix, Matrix]:
    """
    İlk ve ikinci yarı için ayrı skor matrisleri üretir.
    Basitleştirme: toplam beklenen golün FIRST_HALF_GOAL_RATIO kadarının ilk
    yarıda, kalanının ikinci yarıda atıldığı varsayılır (istatistiksel ortalama).
    """
    lh1, la1 = lambda_home * FIRST_HALF_GOAL_RATIO, lambda_away * FIRST_HALF_GOAL_RATIO
    lh2, la2 = lambda_home * (1 - FIRST_HALF_GOAL_RATIO), lambda_away * (1 - FIRST_HALF_GOAL_RATIO)
    return build_score_matrix(lh1, la1), build_score_matrix(lh2, la2)


def _iy_ms_combinations(first_half_matrix: Matrix, full_match_matrix: Matrix) -> Dict[str, float]:
    """
    İY/MS (İlk Yarı / Maç Sonucu) 9 kombinasyonunu, ilk yarı ve maç sonucu
    olasılıklarının BAĞIMSIZ olduğu basitleştirilmiş varsayımıyla hesaplar.
    NOT: Gerçekte iki değişken tam bağımsız değildir; bu bir yaklaşıklıktır.
    """
    iy = _match_result_probs(first_half_matrix)
    ms = _match_result_probs(full_match_matrix)
    combos = {}
    for iy_key, iy_label in [("MS1", "1"), ("MSX", "X"), ("MS2", "2")]:
        for ms_key, ms_label in [("MS1", "1"), ("MSX", "X"), ("MS2", "2")]:
            combos[f"IY{iy_label}/MS{ms_label}"] = iy[iy_key] * ms[ms_key]
    return combos


def analyze_fixture(fixture: Fixture) -> AnalysisResult:
    """Bir Fixture için tüm pazarları hesaplayıp AnalysisResult döndürür."""
    lambda_home, lambda_away = compute_expected_goals(fixture)
    matrix = build_score_matrix(lambda_home, lambda_away)
    fh_matrix, sh_matrix = _half_matrices(lambda_home, lambda_away)

    home_marginal = _row_sums(matrix)   # ev sahibinin gol dağılımı
    away_marginal = _col_sums(matrix)   # deplasmanın gol dağılımı

    probabilities: Dict[str, float] = {}
    probabilities.update(_match_result_probs(matrix))
    probabilities.update(_btts_probs(matrix))
    for line in (1.5, 2.5, 3.5):
        probabilities.update(_over_under_probs(matrix, line))

    # En çok gol olacak yarı
    fh_expected = lambda_home * FIRST_HALF_GOAL_RATIO + lambda_away * FIRST_HALF_GOAL_RATIO
    sh_expected = (lambda_home + lambda_away) - fh_expected
    total_half = fh_expected + sh_expected
    probabilities["1_YARI_COK_GOLLU"] = fh_expected / total_half if total_half else 0.5
    probabilities["2_YARI_COK_GOLLU"] = sh_expected / total_half if total_half else 0.5

    # IY/MS kombinasyonları
    probabilities.update(_iy_ms_combinations(fh_matrix, matrix))

    # Sadece ilk yarı / sadece ikinci yarı sonucu
    fh_result = _match_result_probs(fh_matrix)
    sh_result = _match_result_probs(sh_matrix)
    probabilities["IY_SADECE_1"] = fh_result["MS1"]
    probabilities["IY_SADECE_X"] = fh_result["MSX"]
    probabilities["IY_SADECE_2"] = fh_result["MS2"]
    probabilities["2Y_SADECE_1"] = sh_result["MS1"]
    probabilities["2Y_SADECE_X"] = sh_result["MSX"]
    probabilities["2Y_SADECE_2"] = sh_result["MS2"]

    # Ev sahibi / deplasman gol alt-üst (1.5 hattı örnek alınmıştır)
    home_ou = _team_goals_over_under(home_marginal, 1.5)
    away_ou = _team_goals_over_under(away_marginal, 1.5)
    probabilities["EV_GOL_UST_1.5"] = home_ou["UST"]
    probabilities["EV_GOL_ALT_1.5"] = home_ou["ALT"]
    probabilities["DEP_GOL_UST_1.5"] = away_ou["UST"]
    probabilities["DEP_GOL_ALT_1.5"] = away_ou["ALT"]

    # Ev galibiyeti + KG var/yok ve Deplasman galibiyeti + KG var/yok kombinasyonları
    n = len(matrix)
    p_home_win_btts_yes = sum(
        matrix[i][j] for i in range(1, n) for j in range(1, n) if i > j
    )
    p_away_win_btts_yes = sum(
        matrix[i][j] for i in range(1, n) for j in range(1, n) if j > i
    )
    probabilities["EV_GALIBIYET_KG_VAR"] = p_home_win_btts_yes
    probabilities["EV_GALIBIYET_KG_YOK"] = probabilities["MS1"] - p_home_win_btts_yes
    probabilities["DEP_GALIBIYET_KG_VAR"] = p_away_win_btts_yes
    probabilities["DEP_GALIBIYET_KG_YOK"] = probabilities["MS2"] - p_away_win_btts_yes

    # --- Öne çıkan / sürpriz seçimler (dürüst çerçeveleme) ---
    sorted_probs = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)

    top_picks = [
        {"market": k, "probability": round(float(v) * 100, 1)}
        for k, v in sorted_probs[:3]
    ]

    surprise_candidates = [
        (k, v) for k, v in sorted_probs if 0.10 <= v <= 0.30
    ]
    surprise_picks = [
        {"market": k, "probability": round(float(v) * 100, 1)}
        for k, v in surprise_candidates[:3]
    ]

    result = AnalysisResult(
        fixture=fixture,
        probabilities={k: round(float(v) * 100, 1) for k, v in probabilities.items()},
        top_picks=top_picks,
        surprise_picks=surprise_picks,
        expected_goals={"home": round(float(lambda_home), 2), "away": round(float(lambda_away), 2)},
    )
    return result
