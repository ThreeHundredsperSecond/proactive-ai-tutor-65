"""Execute the saved notebook again, saving a separate immutable replay."""
import os
import nbformat
from nbclient import NotebookClient
from fipi_extension import ROOT, RUN, freeze


def main():
    source=RUN/'derived/checkpoint-100-v1/review.ipynb'
    target=RUN/'checks/checkpoint100-replay.ipynb'
    if target.exists():
        print('Saved replay already exists; not overwritten.');return
    nb=nbformat.read(source,as_version=4)
    previous=os.environ.get('PATH','')
    os.environ['PATH']=str(ROOT/'.venv/Scripts')+os.pathsep+previous
    try:
        NotebookClient(nb,timeout=120,startup_timeout=30,resources={'metadata':{'path':str(ROOT)}}).execute()
    finally:
        os.environ['PATH']=previous
    freeze(target,nbformat.writes(nb))
    print(target)


if __name__=='__main__':main()
