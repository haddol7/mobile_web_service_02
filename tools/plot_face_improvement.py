"""Plot before/after results measured on the same final unseen-identity clips."""
import hashlib
import json
from pathlib import Path
import os
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def main():
    if platform.system()!="Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run inside WSL.")
    record=ROOT/"evidence/person-libraries/face-improvement-evaluation.json"
    result=json.loads(record.read_text())
    conditions=["original","low_light_35_percent","low_resolution_64px"]
    labels=["Original","Low light 35%","64px downsample"]
    before=[result["comparisons"][k]["legacy"]["known_recall"]*100 for k in conditions]
    after=[result["comparisons"][k]["improved"]["known_recall"]*100 for k in conditions]
    fig,axis=plt.subplots(figsize=(10,6),dpi=150)
    fig.subplots_adjust(left=.09,right=.98,top=.78,bottom=.28)
    x=np.arange(3);width=.32
    old=axis.bar(x-width/2,before,width,color="#aab5ae",label="Previous")
    new=axis.bar(x+width/2,after,width,color="#276650",label="Improved")
    axis.bar_label(old,labels=[f"{v:.1f}%" for v in before],padding=4,fontsize=11)
    axis.bar_label(new,labels=[f"{v:.1f}%" for v in after],padding=4,fontsize=11)
    axis.set_ylim(0,112);axis.set_yticks([0,20,40,60,80,100]);axis.set_ylabel("Correct candidate / enrolled-person sampled frames (%)")
    axis.set_xticks(x,labels);axis.legend(loc="upper left",frameon=False,ncol=2)
    axis.spines[["top","right"]].set_visible(False)
    fig.suptitle("Face matching improvement on held-out identities",fontsize=17,y=.97)
    fig.text(.5,.88,"24 identity IDs, 48 query clips, 576 distinct sampled frames",ha="center",fontsize=11)
    parts=[]
    for label,condition in zip(labels,conditions):
        row=result["comparisons"][condition]["improved"]
        parts.append(label+f': {row["unknown_false_candidates"]}/{row["unknown_frames"]}')
    fig.text(.5,.15,"Improved unknown-person false candidates",ha="center",fontsize=11,fontweight="bold")
    fig.text(.5,.105,"    ".join(parts),ha="center",fontsize=10)
    fig.text(.5,.04,"Same pretrained model. No training. Transformed conditions share the original frames.",ha="center",fontsize=9)
    image=ROOT/"evidence/person-libraries/face-improvement-results.png"
    fig.savefig(image);plt.close(fig)
    result["comparison_chart"]=str(image.relative_to(ROOT))
    result["comparison_chart_sha256"]=hashlib.sha256(image.read_bytes()).hexdigest()
    result["chart_renderer_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    record.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"chart":str(image.relative_to(ROOT)),"before":before,"after":after}))


if __name__=="__main__":
    main()
