# -*- coding: utf-8 -*-
"""
main.py
-------
Kolik uygulamasının Kivy giriş noktası.
"""

import threading
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.clock import mainthread
from kivy.metrics import dp
from datetime import datetime, timedelta

import data_fetcher
from analyzer import analyze_fixture
from market_labels import market_label

KV_FILE = "kolik.kv"

# Varsayılan lig kodu BOŞ = tüm ligler taranır
DEFAULT_LEAGUE_CODE = ""

DATE_RANGE_OPTIONS = ["Bugun", "Bu Hafta (7 gun)", "Bu Ay (30 gun)", "Tum Yaklasanlar"]


def _date_range_for_option(option: str):
    today = datetime.utcnow().date()
    if option == "Bugun":
        return today.isoformat(), today.isoformat()
    if option == "Bu Hafta (7 gun)":
        return today.isoformat(), (today + timedelta(days=7)).isoformat()
    if option == "Bu Ay (30 gun)":
        return today.isoformat(), (today + timedelta(days=30)).isoformat()
    return None, None


class MatchRow(BoxLayout):
    home_team = StringProperty("")
    away_team = StringProperty("")
    league = StringProperty("")
    kickoff = StringProperty("")
    raw_fixture = None


class BultenScreen(Screen):
    loading = BooleanProperty(False)
    status_text = StringProperty("Bülten yüklemek için 'Yenile' butonuna basın.")

    def refresh_fixtures(self, league_code: str = DEFAULT_LEAGUE_CODE, date_option: str = "Bugun"):
        self.loading = True
        self.status_text = "Bülten yükleniyor..."
        self.ids.match_list.clear_widgets()
        date_from, date_to = _date_range_for_option(date_option)
        threading.Thread(
            target=self._fetch_worker,
            args=(league_code, date_from, date_to),
            daemon=True,
        ).start()

    def _fetch_worker(self, league_code: str, date_from, date_to):
        try:
            fixtures = data_fetcher.fetch_upcoming_fixtures(
                league_code, limit=40, date_from=date_from, date_to=date_to
            )
            self._on_fixtures_loaded(fixtures)
        except Exception as e:
            import traceback
            from kivy.logger import Logger
            Logger.error("KOLIK: TAM HATA:\n" + traceback.format_exc())
            self._on_error(str(e))

    @mainthread
    def _on_fixtures_loaded(self, fixtures):
        self.loading = False
        if not fixtures:
            self.status_text = "Bu filtrede yaklaşan maç bulunamadı."
            return
        self.status_text = f"{len(fixtures)} maç bulundu."
        for fx in fixtures:
            row = MatchRow(
                home_team=fx["home"], away_team=fx["away"],
                league=fx.get("league", ""), kickoff=fx.get("utc_date", "")[:16].replace("T", " ")
            )
            row.raw_fixture = fx
            row.ids.select_btn.bind(on_release=lambda inst, f=fx: self.go_to_analysis(f))
            self.ids.match_list.add_widget(row)

    @mainthread
    def _on_error(self, message: str):
        self.loading = False
        self.status_text = f"Hata: {message}\n(API anahtarınızı kontrol edin.)"

    def go_to_analysis(self, raw_fixture: dict):
        app = App.get_running_app()
        app.root.get_screen("analiz").load_fixture(raw_fixture)
        app.root.current = "analiz"


class AnalizScreen(Screen):
    loading = BooleanProperty(False)
    status_text = StringProperty("")
    home_team = StringProperty("")
    away_team = StringProperty("")

    def load_fixture(self, raw_fixture: dict):
        self.home_team = raw_fixture["home"]
        self.away_team = raw_fixture["away"]
        self.loading = True
        self.status_text = "Takım formu, H2H ve hava durumu verileri toplanıyor..."
        self.ids.results_box.clear_widgets()
        threading.Thread(target=self._analyze_worker, args=(raw_fixture,), daemon=True).start()

    def _analyze_worker(self, raw_fixture: dict):
        try:
            fixture = data_fetcher.build_fixture(raw_fixture)
            result = analyze_fixture(fixture)
            self._on_analysis_done(result)
        except Exception as e:
            import traceback
            from kivy.logger import Logger
            Logger.error("KOLIK: TAM HATA:\n" + traceback.format_exc())
            self._on_error(str(e))

    @mainthread
    def _on_analysis_done(self, result):
        self.loading = False
        self.status_text = ""
        box = self.ids.results_box

        eg = result.expected_goals
        box.add_widget(self._section_title(
            f"Beklenen Gol (xG benzeri): {self.home_team} {eg['home']}  -  {eg['away']} {self.away_team}"
        ))

        box.add_widget(self._section_title("İSTATİSTİKSEL OLARAK ÖNE ÇIKAN SEÇİMLER"))
        for pick in result.top_picks:
            box.add_widget(self._pick_row(market_label(pick["market"]), pick["probability"]))

        box.add_widget(self._section_title("DÜŞÜK OLASILIKLI SÜRPRİZ SENARYOLAR"))
        if result.surprise_picks:
            for pick in result.surprise_picks:
                box.add_widget(self._pick_row(market_label(pick["market"]), pick["probability"]))
        else:
            lbl = Label(text="Bu maç için belirgin bir sürpriz senaryo bulunamadı.",
                        size_hint_y=None, height=dp(30), halign="center")
            lbl.text_size = (box.width, None)
            box.add_widget(lbl)

        box.add_widget(self._section_title("TÜM PAZARLAR (Detaylı Olasılık Tablosu)"))
        for market, prob in sorted(result.probabilities.items()):
            box.add_widget(self._pick_row(market_label(market), prob, small=True))

        note_label = Label(
            text=result.confidence_note,
            size_hint_y=None, height=dp(60), color=(0.85, 0.72, 0.25, 1),
            italic=True, halign="center", valign="middle"
        )
        note_label.text_size = (box.width, None)
        box.add_widget(note_label)

    @mainthread
    def _on_error(self, message: str):
        self.loading = False
        self.status_text = f"Hata: {message}"

    def _section_title(self, text):
        lbl = Label(text=text, bold=True, size_hint_y=None, height=dp(44),
                     color=(0.83, 0.68, 0.21, 1), halign="center", valign="middle")
        lbl.text_size = (self.ids.results_box.width, None)
        return lbl

    def _pick_row(self, market, prob, small=False):
        row = BoxLayout(size_hint_y=None, height=dp(30 if small else 40),
                         padding=[dp(4), 0])
        market_lbl = Label(text=market, halign="left", valign="middle",
                            color=(0.9, 0.9, 0.9, 1), font_size="11sp" if small else "13sp")
        market_lbl.text_size = (self.ids.results_box.width * 0.68, None)
        row.add_widget(market_lbl)
        row.add_widget(Label(text=f"%{prob}", halign="right", bold=not small,
                              color=(0.13, 0.55, 0.36, 1)))
        return row


class KolikScreenManager(ScreenManager):
    pass


class KolikApp(App):
    title = "Kolik"

    def build(self):
        Builder.load_file(KV_FILE)
        sm = KolikScreenManager()
        sm.add_widget(BultenScreen(name="bulten"))
        sm.add_widget(AnalizScreen(name="analiz"))
        return sm


if __name__ == "__main__":
    KolikApp().run()
