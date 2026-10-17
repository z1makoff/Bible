#!/bin/sh
# Создаёт ярлык «Читалка» в меню приложений и на рабочем столе (Linux).
# Запускать один раз после переноса папки: sh app/install_linux.sh
# Если папку потом переместить, запустите снова: ярлык хранит полный путь.
set -e
APP=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$APP")
chmod +x "$APP/launch.sh"

ENTRY="[Desktop Entry]
Type=Application
Name=Читалка
Comment=Ветхий Завет: перевод без готовой трактовки
Exec=\"$APP/launch.sh\"
Path=$ROOT
Icon=accessories-dictionary
Terminal=false
Categories=Education;"

MENU="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$MENU"
printf '%s\n' "$ENTRY" > "$MENU/chitalka.desktop"
chmod +x "$MENU/chitalka.desktop"
echo "Ярлык в меню приложений: $MENU/chitalka.desktop"

DESK=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
if [ -d "$DESK" ]; then
    cp "$MENU/chitalka.desktop" "$DESK/chitalka.desktop"
    chmod +x "$DESK/chitalka.desktop"
    gio set "$DESK/chitalka.desktop" metadata::trusted true 2>/dev/null || true
    echo "Ярлык на рабочем столе: $DESK/chitalka.desktop"
    echo "Если рабочий стол спросит, разрешить ли запуск, выберите «Разрешить запуск»."
fi
