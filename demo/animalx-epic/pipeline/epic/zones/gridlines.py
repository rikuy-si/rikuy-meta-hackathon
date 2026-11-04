import cv2,sys
for f in sys.argv[1:]:
    im=cv2.imread(f)
    for x in range(0,1280,80):
        cv2.line(im,(x,0),(x,719),(0,255,255),1); cv2.putText(im,str(x),(x+2,12),0,0.35,(0,255,255),1)
    for y in range(0,720,80):
        cv2.line(im,(0,y),(1279,y),(0,255,255),1); cv2.putText(im,str(y),(2,y-2),0,0.35,(0,255,255),1)
    cv2.imwrite(f.replace('frame_','g_'),im)
