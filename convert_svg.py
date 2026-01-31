import Cocoa
import sys
import os

def convert_svg_to_png(svg_path, png_path, size=1024):
    if not os.path.exists(svg_path):
        print(f"Error: {svg_path} not found")
        sys.exit(1)
        
    url = Cocoa.NSURL.fileURLWithPath_(os.path.abspath(svg_path))
    img = Cocoa.NSImage.alloc().initWithContentsOfURL_(url)
    
    if not img or not img.isValid():
        print(f"Error loading {svg_path}")
        sys.exit(1)
    
    out_rect = Cocoa.NSMakeRect(0, 0, size, size)
    new_img = Cocoa.NSImage.alloc().initWithSize_(out_rect.size)
    
    new_img.lockFocus()
    img.drawInRect_fromRect_operation_fraction_(out_rect, Cocoa.NSZeroRect, Cocoa.NSCompositeSourceOver, 1.0)
    new_img.unlockFocus()
    
    tiff_data = new_img.TIFFRepresentation()
    bitmap = Cocoa.NSBitmapImageRep.imageRepWithData_(tiff_data)
    png_data = bitmap.representationUsingType_properties_(Cocoa.NSBitmapImageFileTypePNG, None)
    
    png_data.writeToFile_atomically_(png_path, True)
    print(f"Converted {svg_path} to {png_path}")

if __name__ == "__main__":
    convert_svg_to_png("test.svg", "icon_source.png")
