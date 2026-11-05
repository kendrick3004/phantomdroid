"""
PhantomDroid — Android Entry Point (Kivy)
Roda o servidor Flask em background e abre o browser automaticamente.
"""
import threading, time, os, sys

# Adiciona o diretório do app ao path
sys.path.insert(0, os.path.dirname(__file__))

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.utils import platform
from kivy.core.window import Window

Window.clearcolor = (0.05, 0.05, 0.1, 1)  # fundo escuro

SERVER_PORT = 8080
_server_started = False


def _start_flask():
    """Inicia o servidor Flask em thread separada."""
    global _server_started
    try:
        from phantomdroid_web import start
        _server_started = True
        start(host="0.0.0.0", port=SERVER_PORT, open_browser=False)
    except Exception as e:
        print(f"[Flask Error] {e}")


def _open_browser(url: str):
    """Abre o navegador no Android."""
    try:
        if platform == "android":
            from android.runnable import run_on_ui_thread
            from jnius import autoclass
            Intent   = autoclass("android.content.Intent")
            Uri      = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")

            @run_on_ui_thread
            def _open():
                intent = Intent(Intent.ACTION_VIEW,
                                Uri.parse(url))
                PythonActivity.mActivity.startActivity(intent)
            _open()
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception as e:
        print(f"[Browser Error] {e}")


class PhantomDroidApp(App):
    def build(self):
        self.title = "PhantomDroid"

        layout = BoxLayout(orientation="vertical",
                           padding=24, spacing=16)

        # Logo
        logo = Label(
            text="[b][color=cc44ff]👻 PhantomDroid[/color][/b]",
            markup=True,
            font_size="26sp",
            size_hint_y=None,
            height=50,
        )

        # Status
        self.status_lbl = Label(
            text="[color=888aaa]Iniciando servidor...[/color]",
            markup=True,
            font_size="14sp",
            size_hint_y=None,
            height=36,
        )

        # Progress bar
        self.pb = ProgressBar(max=100, value=0,
                              size_hint_y=None, height=10)

        # Botão principal
        self.btn = Button(
            text="⏳ Aguarde...",
            font_size="16sp",
            background_color=(0.8, 0.27, 1, 1),
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=56,
            disabled=True,
        )
        self.btn.bind(on_press=self.open_panel)

        # Info
        info = Label(
            text=(
                "[color=888aaa]"
                "O painel web roda localmente.\n"
                "Funciona offline — sem internet necessária.\n"
                "[color=ff3355]Apenas para uso autorizado.[/color]"
                "[/color]"
            ),
            markup=True,
            font_size="12sp",
            halign="center",
        )

        layout.add_widget(Label(size_hint_y=0.1))  # spacer
        layout.add_widget(logo)
        layout.add_widget(self.status_lbl)
        layout.add_widget(self.pb)
        layout.add_widget(self.btn)
        layout.add_widget(info)
        layout.add_widget(Label(size_hint_y=0.3))  # spacer

        # Inicia Flask em background
        t = threading.Thread(target=_start_flask, daemon=True)
        t.start()

        # Verifica quando o servidor está pronto
        Clock.schedule_interval(self._check_server, 0.5)

        return layout

    def _check_server(self, dt):
        global _server_started
        self.pb.value = min(self.pb.value + 8, 95)

        if _server_started:
            # Espera mais um pouco para o Flask iniciar
            Clock.unschedule(self._check_server)
            Clock.schedule_once(self._server_ready, 1.0)

    def _server_ready(self, dt):
        self.pb.value = 100
        self.status_lbl.text = (
            "[color=00cc77]✓ Servidor ativo na porta "
            f"{SERVER_PORT}[/color]"
        )
        self.btn.text = "🌐 Abrir Painel de Controle"
        self.btn.disabled = False

    def open_panel(self, instance):
        url = f"http://127.0.0.1:{SERVER_PORT}"
        self.status_lbl.text = (
            f"[color=cc44ff]Abrindo {url}...[/color]"
        )
        _open_browser(url)


if __name__ == "__main__":
    PhantomDroidApp().run()
