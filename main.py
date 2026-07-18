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
from kivy.properties import StringProperty, BooleanProperty
from kivy.clock import mainthread
from kivy.metrics import dp
from datetime import datetime, timedelta, date

import data_fetcher
from analyzer import analyze_fixture, evaluate_actual_result
from market_labels import market_label

KV_FILE = "kolik.kv"

_TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
              "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
_TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _format_date_tr(d: date) -> str:
    return f"{d.day} {_TR_MONTHS[d.month - 1]} {d.year}  ({_TR_DAYS[d.weekday()]})"


class MatchRow(BoxLayout):
    home_team = StringProperty("")
    away_team = StringProperty("")
    league = StringProperty("")
    kickoff = StringProperty("")
    raw_fixture = None


class BultenScreen(Screen):
    loading = BooleanProperty(False)
    status_text = StringProperty("Bülten yüklemek için 'Yenile' butonuna basın.")
    date_display = StringProperty("")

    def on_kv_post(self, base_widget):
        self.selected_date = datetime.utcnow().date()
        self.date_display = _format_date_tr(self.selected_date)
        self._all_fixtures = []
        self._search_mode = False

    def shift_date(self, delta_days: int):
        self.selected_date += timedelta(days=delta_days)
        self.date_display = _format_date_tr(self.selected_date)
        self.ids.search_input.text = ""
        self._search_mode = False
        self.refresh_fixtures()

    def smart_refresh(self):
        """
        'Yenile' butonuna basılınca çağrılır. Arama kutusunda yazı varsa
        o takımı TARİHTEN BAĞIMSIZ arar; boşsa seçili günün maçlarını getirir.
        """
        query = self.ids.search_input.text.strip()
        if query:
            self.search_team_wide(query)
        else:
            self.refresh_fixtures()

    def refresh_fixtures(self):
        self.loading = True
        self.status_text = "Bülten yükleniyor..."
        self._search_mode = False
        self.ids.match_list.clear_widgets()
        date_str = self.selected_date.isoformat()
        threading.Thread(
            target=self._fetch_worker,
            args=(date_str, date_str),
            daemon=True,
        ).start()

    def _fetch_worker(self, date_from, date_to):
        try:
            fixtures = data_fetcher.fetch_upcoming_fixtures(
                "", limit=80, date_from=date_from, date_to=date_to
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
        self._all_fixtures = fixtures
        if not fixtures:
            self.status_text = f"{self.date_display} tarihinde maç bulunamadı."
        else:
            self.status_text = f"{len(fixtures)} maç bulundu ({self.date_display})."
        self._render_fixtures(fixtures)

    def _render_fixtures(self, fixtures):
        self.ids.match_list.clear_widgets()
        for fx in fixtures:
            is_finished = fx.get("status") == "FINISHED"
            if is_finished and fx.get("home_goals") is not None:
                second_line = f"{fx.get('league','')}  |  Sonuc: {fx['home_goals']}-{fx['away_goals']} (Bitti)"
            else:
                second_line = f"{fx.get('league','')}  |  {fx.get('utc_date','')[:16].replace('T',' ')}"

            row = MatchRow(
                home_team=fx["home"], away_team=fx["away"],
                league=second_line, kickoff=""
            )
            row.raw_fixture = fx
            row.ids.select_btn.text = "Sonucu Gor" if is_finished else "Analiz Et"
            row.ids.select_btn.bind(on_release=lambda inst, f=fx: self.go_to_analysis(f))
            self.ids.match_list.add_widget(row)

    def filter_matches(self, query: str):
        """Yazarken YEREL (o an yüklü listede) hızlı filtre yapar."""
        if self._search_mode:
            return
        query = (query or "").strip().lower()
        if not query:
            self._render_fixtures(self._all_fixtures)
            return
        filtered = [
            fx for fx in self._all_fixtures
            if query in fx["home"].lower() or query in fx["away"].lower()
        ]
        self._render_fixtures(filtered)

    def search_team_wide(self, query: str):
        """TARİHTEN BAĞIMSIZ olarak (son 7 gün - gelecek 60 gün) o takımı arar."""
        query = (query or "").strip()
        if not query:
            return
        self.loading = True
        self.status_text = f"\"{query}\" tum tarihlerde araniyor..."
        self.ids.match_list.clear_widgets()
        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query: str):
        try:
            today = datetime.utcnow().date()
            date_from = (today - timedelta(days=7)).isoformat()
            date_to = (today + timedelta(days=60)).isoformat()
            fixtures = data_fetcher.fetch_upcoming_fixtures(
                "", limit=300, date_from=date_from, date_to=date_to
            )
            q = query.lower()
            filtered = [
                fx for fx in fixtures
                if q in fx["home"].lower() or q in fx["away"].lower()
            ]
            self._on_search_done(filtered, query)
        except Exception as e:
            import traceback
            from kivy.logger import Logger
            Logger.error("KOLIK: TAM HATA:\n" + traceback.format_exc())
            self._on_error(str(e))

    @mainthread
    def _on_search_done(self, filtered, query):
        self.loading = False
        self._search_mode = True
        self._all_fixtures = filtered
        if not filtered:
            self.status_text = f"\"{query}\" icin sonuc bulunamadi (son 7 gun - gelecek 60 gun araliginda)."
        else:
            self.status_text = f"\"{query}\" icin {len(filtered)} mac bulundu (tum tarihler)."
        self._render_fixtures(filtered)

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
            self._on_analysis_done(result, raw_fixture)
        except Exception as e:
            import traceback
            from kivy.logger import Logger
            Logger.error("KOLIK: TAM HATA:\n" + traceback.format_exc())
            self._on_error(str(e))

    @mainthread
    def _on_analysis_done(self, result, raw_fixture):
        self.loading = False
        self.status_text = ""
        box = self.ids.results_box

        is_finished = raw_fixture.get("status") == "FINISHED" and raw_fixture.get("home_goals") is not None
        hit_markets = set()
        if is_finished:
            hit_markets = evaluate_actual_result(
                raw_fixture["home_goals"], raw_fixture["away_goals"],
                raw_fixture.get("ht_home_goals"), raw_fixture.get("ht_away_goals"),
            )
            score_lbl = Label(
                text=f"GERCEKLESEN SONUC: {self.home_team} {raw_fixture['home_goals']} - {raw_fixture['away_goals']} {self.away_team}",
                bold=True, size_hint_y=None, height=dp(40),
                color=(0.13, 0.75, 0.45, 1), halign="center", valign="middle"
            )
            score_lbl.text_size = (box.width, None)
            box.add_widget(score_lbl)
            hint_lbl = Label(
                text="Yesil + isaretli satirlar gercekte TUTAN tahminlerdir.",
                size_hint_y=None, height=dp(24), font_size="11sp",
                color=(0.831, 0.686, 0.216, 0.8), halign="center", valign="middle"
            )
            hint_lbl.text_size = (box.width, None)
            box.add_widget(hint_lbl)

        eg = result.expected_goals
        box.add_widget(self._section_title(
            f"Beklenen Gol (xG benzeri): {self.home_team} {eg['home']}  -  {eg['away']} {self.away_team}"
        ))

        box.add_widget(self._section_title("İSTATİSTİKSEL OLARAK ÖNE ÇIKAN SEÇİMLER"))
        for pick in result.top_picks:
            box.add_widget(self._pick_row(pick["market"], pick["probability"], pick["market"] in hit_markets))

        box.add_widget(self._section_title("DÜŞÜK OLASILIKLI SÜRPRİZ SENARYOLAR"))
        if result.surprise_picks:
            for pick in result.surprise_picks:
                box.add_widget(self._pick_row(pick["market"], pick["probability"], pick["market"] in hit_markets))
        else:
            lbl = Label(text="Bu maç için belirgin bir sürpriz senaryo bulunamadı.",
                        size_hint_y=None, height=dp(30), halign="center")
            lbl.text_size = (box.width, None)
            box.add_widget(lbl)

        box.add_widget(self._section_title("TÜM PAZARLAR (Detaylı Olasılık Tablosu)"))
        for market, prob in sorted(result.probabilities.items()):
            box.add_widget(self._pick_row(market, prob, market in hit_markets, small=True))

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

    def _pick_row(self, market_code, prob, hit=False, small=False):
        row = BoxLayout(size_hint_y=None, height=dp(30 if small else 40),
                         padding=[dp(4), 0])
        label_text = market_label(market_code)
        if hit:
            label_text = "✓ " + label_text
        market_color = (0.20, 0.85, 0.45, 1) if hit else (0.9, 0.9, 0.9, 1)
        market_lbl = Label(text=label_text, halign="left", valign="middle",
                            color=market_color, bold=hit,
                            font_size="11sp" if small else "13sp")
        market_lbl.text_size = (self.ids.results_box.width * 0.68, None)
        row.add_widget(market_lbl)

        prob_color = (0.20, 0.85, 0.45, 1) if hit else (0.13, 0.55, 0.36, 1)
        row.add_widget(Label(text=f"%{prob}", halign="right", bold=(not small) or hit,
                              color=prob_color))
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
