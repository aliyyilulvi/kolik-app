# -*- coding: utf-8 -*-
"""
data_fetcher.py
----------------
Kolik uygulamasının veri toplama katmanı.

ÖNEMLİ TASARIM KARARI:
Bu modül KESİNLİKLE bahis sitelerinden (Nesine, Misli, Bilyoner vb.) veri
scrape etmez. Bunun yerine:

  1) Fikstür + geçmiş maç sonuçları  -> football-data.org REST API'si
     (ücretsiz katmanı var, kişisel API anahtarı gerektirir, ToS'a uygundur)
  2) Hava durumu                     -> Open-Meteo API (anahtar gerekmez, açık veri)
  3) Kadro piyasa değeri             -> Transfermarkt'ın resmi bir API'si yoktur ve
     sitesini scrape etmek ToS ihlalidir. Bu yüzden kullanıcı bu veriyi
     data/market_values.csv dosyasına KENDİSİ girer (manuel/opsiyonel).
     Girilmezse analiz motoru bu faktörü nötr (1.0) kabul eder.

API ANAHTARI:
Mobilde (Android) ortam değişkeni (environment variable) ayarlamak mümkün
olmadığı için API anahtarı doğrudan aşağıdaki _HARDCODED_API_KEY sabitine
gömülüdür.
"""

import os
import csv
from datetime import datetime
from typing import List, Optional

import requests

from models import MatchResult, TeamStats, HeadToHead, WeatherInfo, Fixture

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"
GEOCODE_BASE = "https://geocoding-api.open-meteo.com/v1/search"

# Mobilde ortam değişkeni çalışmadığı için API anahtarı doğrudan buraya gömülüdür.
_HARDCODED_API_KEY = "6fdc17feb0d5436782e4382f3a1daa86"


def _api_key() -> str:
    key = _HARDCODED_API_KEY or os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if not key:
        raise RuntimeError(
            "FOOTBALL_DATA_API_KEY tanımlı değil. Ücretsiz anahtar için: "
            "https://www.football-data.org/client/register"
        )
    return key


def _headers() -> dict:
    return {"X-Auth-Token": _api_key()}


# ----------------------------------------------------------------------
# 1) FİKSTÜR (Bülten) ÇEKME
# ----------------------------------------------------------------------
def fetch_upcoming_fixtures(competition_code: str = "PL", limit: int = 20) -> List[dict]:
    """
    Belirtilen ligin yaklaşan maçlarını döndürür.
    competition_code örnekleri: "PL" (İngiltere), "PD" (İspanya), "SA" (İtalya),
    "BL1" (Almanya), "TR1" (Türkiye Süper Lig - destekleniyorsa).
    Dönüş: [{"home": "...", "away": "...", "home_id":.., "away_id":.., "utc_date":..., "league":...}, ...]
    """
    url = f"{FOOTBALL_DATA_BASE}/competitions/{competition_code}/matches"
    params = {"status": "SCHEDULED"}
    resp = requests.get(url, headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    fixtures = []
    for m in data.get("matches", [])[:limit]:
        fixtures.append({
            "home": m["homeTeam"]["name"],
            "away": m["awayTeam"]["name"],
            "home_id": m["homeTeam"]["id"],
            "away_id": m["awayTeam"]["id"],
            "utc_date": m["utcDate"],
            "league": data.get("competition", {}).get("name", competition_code),
        })
    return fixtures


# ----------------------------------------------------------------------
# 2) TAKIM FORMU (son 5 genel, son 3 ev/deplasman)
# ----------------------------------------------------------------------
def fetch_team_recent_matches(team_id: int, limit: int = 10) -> List[MatchResult]:
    """Bir takımın oynadığı son maçları (FINISHED) çeker."""
    url = f"{FOOTBALL_DATA_BASE}/teams/{team_id}/matches"
    params = {"status": "FINISHED", "limit": limit}
    resp = requests.get(url, headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for m in data.get("matches", []):
        is_home = m["homeTeam"]["id"] == team_id
        gf = m["score"]["fullTime"]["home"] if is_home else m["score"]["fullTime"]["away"]
        ga = m["score"]["fullTime"]["away"] if is_home else m["score"]["fullTime"]["home"]
        if gf is None or ga is None:
            continue
        opponent = m["awayTeam"]["name"] if is_home else m["homeTeam"]["name"]
        results.append(MatchResult(
            opponent=opponent, home=is_home,
            goals_for=gf, goals_against=ga, date=m.get("utcDate", "")
        ))
    return results


def build_team_stats(team_name: str, team_id: int) -> TeamStats:
    """Bir takım için TeamStats nesnesini son maç verileriyle doldurur."""
    all_recent = fetch_team_recent_matches(team_id, limit=10)
    last5 = all_recent[:5]
    # Sadece ev sahibiyken oynadığı / sadece deplasmandayken oynadığı son 3 maç
    home_or_away_specific = [m for m in all_recent if m.home][:3]  # çağıran taraf belirleyecek

    stats = TeamStats(name=team_name, last5_all=last5, last3_home_or_away=home_or_away_specific)
    # Kadro değeri varsa CSV'den yükle
    stats.squad_market_value_eur = load_market_value(team_name)
    return stats


def fetch_head_to_head(match_id: int, limit: int = 5) -> HeadToHead:
    """İki takım arasındaki geçmiş karşılaşmaları çeker (football-data.org head2head endpoint)."""
    url = f"{FOOTBALL_DATA_BASE}/matches/{match_id}/head2head"
    params = {"limit": limit}
    resp = requests.get(url, headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    matches = []
    for m in data.get("matches", []):
        matches.append({
            "home_team": m["homeTeam"]["name"],
            "away_team": m["awayTeam"]["name"],
            "home_goals": m["score"]["fullTime"]["home"],
            "away_goals": m["score"]["fullTime"]["away"],
            "date": m.get("utcDate", ""),
        })
    return HeadToHead(matches=matches)


# ----------------------------------------------------------------------
# 3) KADRO PİYASA DEĞERİ (manuel CSV - Transfermarkt scrape edilmez)
# ----------------------------------------------------------------------
_MARKET_VALUE_CSV = os.path.join(os.path.dirname(__file__), "data", "market_values.csv")


def load_market_value(team_name: str) -> float:
    """
    data/market_values.csv dosyasından takımın kadro değerini (EUR) okur.
    Dosya formatı: team_name,market_value_eur
    Bu dosyayı kullanıcı Transfermarkt'ta gördüğü GÜNCEL değeri elle girerek
    kendisi doldurur (siteyi otomatik scrape etmiyoruz).
    """
    if not os.path.exists(_MARKET_VALUE_CSV):
        return 0.0
    with open(_MARKET_VALUE_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["team_name"].strip().lower() == team_name.strip().lower():
                try:
                    return float(row["market_value_eur"])
                except (ValueError, KeyError):
                    return 0.0
    return 0.0


# ----------------------------------------------------------------------
# 4) HAVA DURUMU (Open-Meteo - ücretsiz, anahtar gerektirmez)
# ----------------------------------------------------------------------
def fetch_city_coordinates(city_name: str) -> Optional[dict]:
    resp = requests.get(GEOCODE_BASE, params={"name": city_name, "count": 1}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results")
    if not results:
        return None
    r = results[0]
    return {"lat": r["latitude"], "lon": r["longitude"]}


def fetch_weather(city_name: str, match_date: str) -> WeatherInfo:
    """
    match_date formatı: 'YYYY-MM-DD'. Maç günü için tahmini hava durumunu döndürür.
    Şehir bulunamazsa veya tarih çok ileri/geri ise nötr WeatherInfo döner.
    """
    coords = fetch_city_coordinates(city_name)
    if not coords:
        return WeatherInfo()

    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "daily": "temperature_2m_max,precipitation_sum,windspeed_10m_max",
        "timezone": "auto",
        "start_date": match_date,
        "end_date": match_date,
    }
    try:
        resp = requests.get(OPEN_METEO_BASE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        temp = daily.get("temperature_2m_max", [None])[0]
        precip = daily.get("precipitation_sum", [None])[0]
        wind = daily.get("windspeed_10m_max", [None])[0]
        condition = "yağışlı" if (precip or 0) > 1 else "açık"
        return WeatherInfo(temperature_c=temp, precipitation_mm=precip,
                            wind_kmh=wind, condition=condition)
    except requests.RequestException:
        return WeatherInfo()


# ----------------------------------------------------------------------
# 5) TÜMÜNÜ BİRLEŞTİREN YÜKSEK SEVİYE FONKSİYON
# ----------------------------------------------------------------------
def build_fixture(raw_fixture: dict) -> Fixture:
    """
    fetch_upcoming_fixtures'tan gelen ham bir kaydı, analiz motoruna
    verilecek tam donanımlı bir Fixture nesnesine çevirir.
    """
    home_stats = build_team_stats(raw_fixture["home"], raw_fixture["home_id"])
    away_stats = build_team_stats(raw_fixture["away"], raw_fixture["away_id"])

    match_date = raw_fixture["utc_date"][:10] if raw_fixture.get("utc_date") else \
        datetime.utcnow().strftime("%Y-%m-%d")

    # Hava durumu için basitçe ev sahibi takım adını "şehir" gibi deniyoruz;
    # gerçek kullanımda stadyum şehri eşleme tablosu eklenmesi önerilir.
    weather = fetch_weather(raw_fixture["home"], match_date)

    return Fixture(
        home_team=raw_fixture["home"],
        away_team=raw_fixture["away"],
        league=raw_fixture.get("league", ""),
        kickoff=raw_fixture.get("utc_date", ""),
        home_stats=home_stats,
        away_stats=away_stats,
        h2h=None,  # match_id varsa fetch_head_to_head ile doldurulabilir
        weather=weather,
    )
