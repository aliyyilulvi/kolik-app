# -*- coding: utf-8 -*-
"""
models.py
---------
Kolik uygulamasında kullanılan veri yapılarını (data class) tanımlar.
Bu dosya, scraper/fetcher ve analiz motoru arasında ortak bir "sözleşme"
görevi görür; böylece veri kaynağı değişse bile analiz motoru etkilenmez.

ÖNEMLİ NOT: Bu uygulama bahis sitelerinden veri çekmez. Veriler açık/lisanslı
spor verisi API'lerinden (örn. football-data.org, API-Football vb.) alınır.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MatchResult:
    """Geçmiş bir maçın özet sonucu (form hesaplamaları için kullanılır)."""
    opponent: str
    home: bool                  # Bu takım o maçta ev sahibi miydi?
    goals_for: int
    goals_against: int
    date: str = ""

    @property
    def points(self) -> int:
        """Galibiyet=3, Beraberlik=1, Mağlubiyet=0 (form skoru için)."""
        if self.goals_for > self.goals_against:
            return 3
        if self.goals_for == self.goals_against:
            return 1
        return 0


@dataclass
class TeamStats:
    """
    Bir takımın analiz için gereken tüm istatistiksel profilini tutar.
    Tüm alanlar data_fetcher.py tarafından doldurulur.
    """
    name: str
    last5_all: List[MatchResult] = field(default_factory=list)      # Genel son 5 maç
    last3_home_or_away: List[MatchResult] = field(default_factory=list)  # Ev/deplasman özel son 3 maç
    squad_market_value_eur: float = 0.0   # Transfermarkt tipi toplam kadro değeri (EUR)

    # Lig ortalamalarına göre normalize edilmiş saldırı/savunma güçleri
    # (analyzer.py tarafından hesaplanıp doldurulur, ham veri değildir)
    attack_strength: float = 1.0
    defense_strength: float = 1.0

    def form_score(self, matches: Optional[List[MatchResult]] = None) -> float:
        """
        Basit ağırlıklı form puanı: en son maç en yüksek ağırlığı taşır.
        Dönüş: 0.0 - 1.0 arası normalize edilmiş form skoru.
        """
        m = matches if matches is not None else self.last5_all
        if not m:
            return 0.5  # Veri yoksa nötr kabul et
        weights = [1.0, 0.85, 0.7, 0.55, 0.4][:len(m)]
        total_w = sum(weights)
        score = sum(mr.points * w for mr, w in zip(m, weights))
        max_score = 3 * total_w
        return score / max_score if max_score else 0.5

    def avg_goals_for(self, matches: Optional[List[MatchResult]] = None) -> float:
        m = matches if matches is not None else self.last5_all
        if not m:
            return 1.2  # lig ortalaması varsayımı
        return sum(x.goals_for for x in m) / len(m)

    def avg_goals_against(self, matches: Optional[List[MatchResult]] = None) -> float:
        m = matches if matches is not None else self.last5_all
        if not m:
            return 1.2
        return sum(x.goals_against for x in m) / len(m)


@dataclass
class HeadToHead:
    """İki takım arasındaki geçmiş karşılaşma özetleri (son 5 maç)."""
    matches: List[dict] = field(default_factory=list)
    # her eleman: {"home_team":..., "away_team":..., "home_goals":..., "away_goals":..., "date":...}


@dataclass
class WeatherInfo:
    """Maç günü hava durumu bilgisi (opsiyonel etkileşim faktörü)."""
    temperature_c: Optional[float] = None
    precipitation_mm: Optional[float] = None
    wind_kmh: Optional[float] = None
    condition: str = "bilinmiyor"

    @property
    def rain_factor(self) -> float:
        """
        Yağışın gol beklentisini hafifçe düşürdüğü varsayımına dayanan
        basit bir çarpan (1.0 = etkisiz, <1.0 = azaltıcı).
        Bu YAKLAŞIK bir varsayımdır, kesin bilimsel katsayı değildir.
        """
        if self.precipitation_mm is None:
            return 1.0
        if self.precipitation_mm > 10:
            return 0.90
        if self.precipitation_mm > 2:
            return 0.96
        return 1.0


@dataclass
class Fixture:
    """Analiz edilecek tek bir maçı temsil eder (bülten satırı)."""
    home_team: str
    away_team: str
    league: str = ""
    kickoff: str = ""
    home_stats: Optional[TeamStats] = None
    away_stats: Optional[TeamStats] = None
    h2h: Optional[HeadToHead] = None
    weather: Optional[WeatherInfo] = None


@dataclass
class AnalysisResult:
    """analyzer.py'nin ürettiği nihai çıktı yapısı (UI bu objeyi render eder)."""
    fixture: Fixture
    probabilities: dict = field(default_factory=dict)     # tüm pazarların olasılıkları
    top_picks: list = field(default_factory=list)          # istatistiksel olarak öne çıkan seçimler
    surprise_picks: list = field(default_factory=list)     # düşük olasılıklı "sürpriz" seçimler
    expected_goals: dict = field(default_factory=dict)      # {"home": 1.6, "away": 1.1}
    confidence_note: str = (
        "Bu oranlar geçmiş verilere dayalı istatistiksel bir modeldir; "
        "gelecekteki maç sonucunun garantisi değildir."
    )
