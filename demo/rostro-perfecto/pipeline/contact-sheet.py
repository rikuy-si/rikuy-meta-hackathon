from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
root=Path(__file__).resolve().parents[1]
sheet=Image.new('RGB',(1600,1908),'#111827')
draw=ImageDraw.Draw(sheet)
for i,path in enumerate(sorted((root/'frames').glob('*afternoon.jpg'))):
    x=(i%2)*800;y=(i//2)*477
    image=ImageOps.contain(Image.open(path),(800,450))
    sheet.paste(image,(x+(800-image.width)//2,y+27))
    draw.text((x+10,y+7),f'CHANNEL {i+1} | 2026-11-03 | ISAPI export first frame',fill='white')
sheet.save(root/'frames/contact-sheet.png')
