# MeuRGB

Controlador RGB por paletas em cima do OpenRGB 1.1 (servidor SDK na porta 6742, roda como admin, driver PawnIO).
App em `app/rgb_controller.py` (servidor local + CLI), interface em `app/index.html` (http://127.0.0.1:6750), aberto pelo `MeuRGB.bat`.
Para ver o hardware detectado: `python app/rgb_controller.py listar`.

## Cores com IA (Claude Color): o usuário descreve um clima e você aplica

Quando o usuário pedir uma paleta, um clima ou um design, monte um perfil e aplique direto:

```bash
cd app && python rgb_controller.py claude - <<'EOF'
{"name": "Nome curto", "description": "Uma frase sobre o visual",
 "colors": ["#FF2E88", "#9B3DFF", "#00D9C8"],
 "mode": "gradiente",
 "brightness": 100, "save": false, "fluir": false, "speed": 3,
 "zones": [{"device": "teclado", "color": "#FFFFFF"},
           {"device": "placa", "zone": "IO Cover", "color": "#FF0000"}],
 "links": {"ram": "span"},
 "exclude": []}
EOF
```

- `mode`: `gradiente`, `alternado` ou `zona` (uma cor da paleta por zona).
- `device` aceita `placa`, `ram`, `teclado`, `mouse`, `gpu`, o id (`0`..) ou parte do nome. `zone` é opcional (parte do nome da zona).
- `links`: como agrupar dispositivos do mesmo tipo (ex.: pentes de RAM). `separate` = cada um com suas cores, `mirror` = iguais, `span` = gradiente contínuo atravessando todos.
- `save: true` grava na memória da placa e das RAMs (continua depois de reiniciar). Use só quando o usuário quiser deixar fixo.
- O perfil aparece no card "Cores com IA" da interface, com histórico, e a tela atualiza sozinha.
- No Claude Code com sandbox, rode esse Bash com `dangerouslyDisableSandbox: true`: o sandbox não enxerga a porta do app.
- Prefira cores vivas e saturadas: cinza e tons escuros ficam feios em LED.

## Convenções

- Interface com ícones SVG (estilo Lucide), nunca emojis. Visual sóbrio: fundo zinc escuro, botão primário branco.
- A lógica de cores existe em dois lugares e precisa ficar igual: `plan_colors` no Python e `plan()` no `index.html`.
