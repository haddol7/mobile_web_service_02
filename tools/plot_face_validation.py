"""Render a readable result chart from saved measurements without rerunning inference."""
import hashlib
import json
from pathlib import Path
import shutil
import os
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT/"evidence/person-libraries"


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run inside WSL.")
    path = PUBLIC/"expanded-face-validation.json"
    result = json.loads(path.read_text())
    private = ROOT/result["private_directory"]
    chart = ROOT/result["chart"]
    if not (private/"initial-validation-result.json").exists():
        shutil.copyfile(path,private/"initial-validation-result.json")
        shutil.copyfile(chart,private/"initial-results-chart.png")
    conditions=result["protocol"]["conditions"]
    names=["Original","Low light 35%","64px downsample"]
    colors={"correct":"#2b765d","unresolved":"#adb8b1","no_face":"#dedede","wrong":"#bb4040"}
    fig,axes=plt.subplots(1,2,figsize=(12,5.3),dpi=140)
    fig.subplots_adjust(top=.76,bottom=.25,left=.13,right=.98,wspace=.36)
    for axis,known in zip(axes,[True,False]):
        keys=(["correct_candidates","known_unresolved","known_no_face","wrong_known_candidates"] if known
              else ["unknown_unresolved","unknown_no_face","unknown_false_candidates"])
        c=[colors[k] for k in (["correct","unresolved","no_face","wrong"] if known else ["unresolved","no_face","wrong"])]
        left=np.zeros(3)
        for key,color in zip(keys,c):
            values=np.array([result["conditions"][condition][key]/(288 if known else 144)*100 for condition in conditions])
            axis.barh(names,values,left=left,color=color,height=.65)
            left+=values
        for i,condition in enumerate(conditions):
            if known:
                value=result["conditions"][condition]["correct_candidates"]/288*100
                axis.text(value/2,i,f"{value:.1f}%",ha="center",va="center",color="white",fontsize=11,fontweight="bold")
            else:
                value=result["conditions"][condition]["unknown_false_candidates"]
                axis.text(50,i,f"{value} false candidates / 144 frames",ha="center",va="center",fontsize=10)
        axis.set_xlim(0,100)
        axis.set_xlabel("Sampled frame conditions (%)",labelpad=10)
        axis.set_title("Planned enrolled people: 12\nSuccessfully enrolled: 11" if known else "Unknown people: 6\n12 query clips",fontsize=12,pad=13)
        axis.tick_params(axis="both",labelsize=10)
    fig.suptitle("Buffalo L: fixed threshold 0.55 and profile margin 0.08",fontsize=15,y=.98)
    fig.text(.5,.89,"18 identity labels, 36 query clips, 432 distinct sampled frames",ha="center",fontsize=11)
    legend=[Patch(color=colors[key],label=label) for key,label in [
        ("correct","Correct candidate"),("unresolved","Unresolved"),("no_face","No face"),("wrong","Wrong candidate")]]
    fig.legend(handles=legend,loc="lower center",bbox_to_anchor=(.5,.07),ncol=4,frameon=False,fontsize=10)
    fig.text(.5,.025,"Low light and low resolution are transformations of the original frames.",ha="center",fontsize=9)
    fig.savefig(chart)
    plt.close(fig)
    result["chart_sha256"]=hashlib.sha256(chart.read_bytes()).hexdigest()
    result["chart_renderer"]={"path":"tools/plot_face_validation.py",
        "sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    path.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"chart":str(chart.relative_to(ROOT)),"sha256":result["chart_sha256"]}))


if __name__ == "__main__":
    main()
