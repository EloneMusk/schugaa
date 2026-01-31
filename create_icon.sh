#!/bin/bash
# Script to create .icns from a source image

# Convert SVG to PNG first
source venv/bin/activate
python convert_svg.py

SOURCE="icon_source.png"
ICONSET="Schugaa.iconset"
OUTPUT="Schugaa.icns"

if [ ! -f "$SOURCE" ]; then
    echo "Source image $SOURCE not found!"
    exit 1
fi

echo "Creating iconset directory..."
mkdir -p "$ICONSET"

echo "Resizing images..."
sips -s format png -z 16 16     "$SOURCE" --out "$ICONSET/icon_16x16.png"
sips -s format png -z 32 32     "$SOURCE" --out "$ICONSET/icon_16x16@2x.png"
sips -s format png -z 32 32     "$SOURCE" --out "$ICONSET/icon_32x32.png"
sips -s format png -z 64 64     "$SOURCE" --out "$ICONSET/icon_32x32@2x.png"
sips -s format png -z 128 128   "$SOURCE" --out "$ICONSET/icon_128x128.png"
sips -s format png -z 256 256   "$SOURCE" --out "$ICONSET/icon_128x128@2x.png"
sips -s format png -z 256 256   "$SOURCE" --out "$ICONSET/icon_256x256.png"
sips -s format png -z 512 512   "$SOURCE" --out "$ICONSET/icon_256x256@2x.png"
sips -s format png -z 512 512   "$SOURCE" --out "$ICONSET/icon_512x512.png"
sips -s format png -z 1024 1024 "$SOURCE" --out "$ICONSET/icon_512x512@2x.png"

echo "Converting iconset to icns..."
iconutil -c icns "$ICONSET" -o "$OUTPUT"

echo "Done. Created $OUTPUT"
rm -rf "$ICONSET"
