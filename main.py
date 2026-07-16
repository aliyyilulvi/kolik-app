# -*- coding: utf-8 -*-
"""
main.py
-------
Kolik uygulamasının Kivy giriş noktası.

Ekranlar:
  - BultenScreen: Ligden gelen yaklaşan maç listesini gösterir.
  - AnalizScreen: Seçilen maç için Poisson tabanlı olasılık analizini gösterir.

ÖNEMLİ: Arayüzde her zaman "olasılık / istatistiksel tahmin" ifadesi
kullanılır; "kesin", "garanti" gibi ifadelerden kaçınılır (bkz. UYARI banner'ı).
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

import data_fetcher
from analyzer import analyze_fixture

KV_FILE = "kolik.kv"

# Uygulama genelinde kullanılacak lig kodu (varsayılan; UI'dan değiştirilebilir)
DEFAULT_LEAGUE_CODE = "PL"


class MatchRow(BoxLayout):
    """Bülten listesindeki tek bir maç satırı."""
    home_team = StringProperty("")
    away_team = StringProperty("")
    league = StringProperty("")
    kickoff = StringProperty("")
    raw_fixture = None  # data_fetcher'dan gelen ham dict burada saklanır


class BultenScreen(Screen):
    """Yaklaşan maçların listelendiği ana ekran."""
    loading = BooleanProperty(False)
    status_text = StringProperty("Bülten yüklemek için 'Yenile' butonuna basın.")

    def refresh_fixtures(self, league_code: str = DEFAULT_LEAGUE_CODE):
        self.loading = True
        self.status_text = "Bülten yükleniyor..."
        self.ids.match_list.clear_widgets()
        threading.Thread(target=self._fetch_worker, args=(league_code,), daemon=True).start()

    def _fetch_worker(self, league_code: str):
        try:
            fixtures = data_fetcher.fetch_upcoming_fixtures(league_code, limit=20)
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
            self.status_text = "Bu ligde yaklaşan maç bulunamadı."
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
    """Seçilen maçın detaylı olasılık analizinin gösterildiği ekran."""
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

        # Beklenen goller
        eg = result.expected_goals
        box.add_widget(self._section_title(
            f"Beklenen Gol (xG benzeri): {self.home_team} {eg['home']}  -  {eg['away']} {self.away_team}"
        ))

        # Öne çıkan istatistiksel seçimler
        box.add_widget(self._section_title("İSTATİSTİKSEL OLARAK ÖNE ÇIKAN SEÇİMLER"))
        for pick in result.top_picks:
            box.add_widget(self._pick_row(pick["market"], pick["probability"]))

        # Sürpriz senaryolar
        box.add_widget(self._section_title("DÜŞÜK OLASILIKLI SÜRPRİZ SENARYOLAR"))
        if result.surprise_picks:
            for pick in result.surprise_picks:
                box.add_widget(self._pick_row(pick["market"], pick["probability"]))
        else:
            box.add_widget(Label(text="Bu maç için belirgin bir sürpriz senaryo bulunamadı.",
                                  size_hint_y=None, height=dp(30)))

        # Tüm pazarlar (detay)
        box.add_widget(self._section_title("TÜM PAZARLAR (Detaylı Olasılık Tablosu)"))
        for market, prob in sorted(result.probabilities.items()):
            box.add_widget(self._pick_row(market, prob, small=True))

        # Şeffaflık notu
        box.add_widget(Label(
            text=result.confidence_note,
            size_hint_y=None, height=dp(60), color=(0.85, 0.72, 0.25, 1),
            italic=True, halign="center", valign="middle"
        ))

    @mainthread
    def _on_error(self, message: str):
        self.loading = False
        self.status_text = f"Hata: {message}"

    def _section_title(self, text):
        lbl = Label(text=text, bold=True, size_hint_y=None, height=dp(36),
                     color=(0.83, 0.68, 0.21, 1))
        return lbl

    def _pick_row(self, market, prob, small=False):
        row = BoxLayout(size_hint_y=None, height=dp(26 if small else 32))
        row.add_widget(Label(text=market, halign="left", color=(0.9, 0.9, 0.9, 1)))
        row.add_widget(Label(text=f"%{prob}", halign="right", bold=not small,
                              color=(0.13, 0.55, 0.36, 1)))
        return row


class KolikScreenManager(ScreenManager):
    pass


class KolikApp(App):
    """Kolik uygulamasının ana App sınıfı."""
    title = "Kolik"

    def build(self):
        Builder.load_file(KV_FILE)
        sm = KolikScreenManager()
        sm.add_widget(BultenScreen(name="bulten"))
        sm.add_widget(AnalizScreen(name="analiz"))
        return sm


if __name__ == "__main__":
    KolikApp().run()
