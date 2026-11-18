<p align="center"><img src="docs/logo.svg" width="72" alt="MeuRGB"></p>

<h1 align="center">MeuRGB <sup>v1</sup></h1>

<p align="center">
Controle o RGB do seu PC por paletas, com prévia ao vivo e <b>cores criadas por IA</b>.<br>
<i>Control your PC's RGB with palettes, live preview and <b>AI-generated colors</b>.</i>
</p>

<p align="center"><img src="docs/screenshot.png" alt="Interface do MeuRGB" width="900"></p>

> **Versão 1 (V1).** Primeira versão pública: funciona bem no dia a dia, mas ainda pode mudar bastante.
> **Version 1 (V1).** First public release: works well day to day, but may still change a lot.

---

## Português

### Destaque: cores com IA
Descreva o clima no chat do **Claude** ("cyberpunk roxo e azul, teclado branco, RAMs contínuas") e ele monta a paleta, ajusta cada dispositivo e aplica na hora. O perfil aparece no card **Cores com IA**, com histórico para reaplicar. As instruções para a IA ficam no [`CLAUDE.md`](CLAUDE.md).

### O que mais faz
- Paleta com seletor de cor próprio: o PC muda **enquanto você escolhe**, e você decide entre **Aplicar** ou **Descartar**.
- Gradiente, alternado ou uma cor por zona, com brilho e efeito **Fluir**.
- Cor manual por zona (placa-mãe, cada RAM, teclado...).
- RAMs **separadas**, **juntas e iguais** ou **juntas e contínuas** (o gradiente atravessa os módulos).
- Tira a paleta de uma imagem (arrastar, colar ou escolher arquivo).
- **Gravar na placa**: as cores continuam depois de reiniciar, sem nada aberto.

### Instalação
Requisitos: Windows 10/11, [Python 3](https://www.python.org/downloads/) e hardware suportado pelo [OpenRGB](https://openrgb.org/devices.html).

1. Baixe o repositório (Code → Download ZIP) e extraia, por exemplo em `C:\MeuRGB`.
2. Abra o **`MeuRGB.bat`**. Na primeira vez ele pede permissão de administrador e:
   baixa o OpenRGB 1.1 oficial, instala a biblioteca `openrgb-python`, instala o driver assinado PawnIO e desativa (sem apagar) a inicialização do ASRock Polychrome.
3. A interface abre no navegador em `http://127.0.0.1:6750`.

Para desfazer: rode `Voltar para ASRock (admin).ps1`.

---

## English

### Highlight: AI colors
Describe a mood in a chat with **Claude** ("purple and blue cyberpunk, white keyboard, continuous RAM") and it builds the palette, tunes each device and applies it instantly. The profile shows up in the **AI colors** card with a history you can re-apply. Instructions for the AI live in [`CLAUDE.md`](CLAUDE.md).

### Features
- Custom color picker with **live preview on your hardware**, then **Apply** or **Discard**.
- Gradient, alternating or one-color-per-zone, with brightness and a **Flow** effect.
- Manual color per zone (motherboard, each RAM stick, keyboard...).
- RAM sticks **separate**, **mirrored** or **continuous** (the gradient spans all sticks).
- Extract a palette from any image.
- **Save to board**: colors persist after reboot with nothing running.

### Install
Requirements: Windows 10/11, [Python 3](https://www.python.org/downloads/) and hardware supported by [OpenRGB](https://openrgb.org/devices.html).

1. Download the repo (Code → Download ZIP) and extract it, e.g. to `C:\MeuRGB`.
2. Run **`MeuRGB.bat`**. On first run it asks for admin rights and downloads official OpenRGB 1.1, installs `openrgb-python`, installs the signed PawnIO driver and disables (without deleting) the ASRock Polychrome startup task.
3. The UI opens at `http://127.0.0.1:6750`.

To undo: run `Voltar para ASRock (admin).ps1`.

---

<sub>Feito com / built on <a href="https://openrgb.org">OpenRGB</a>, <a href="https://github.com/namazso/PawnIO.Setup">PawnIO</a> e <a href="https://github.com/jath03/openrgb-python">openrgb-python</a>. Use por sua conta e risco / use at your own risk. Licença / License: MIT.</sub>
