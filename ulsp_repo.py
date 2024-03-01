import urllib.request
import io
import os
import sys
import shutil
import pathlib
from urllib.parse import urlparse
import json
# dependencies
from PIL import Image, ImageDraw, ImageFont
import qrcode

# https://github.com/PyGithub/PyGithub
# more: https://stackoverflow.com/questions/49458329/create-clone-and-push-to-github-repo-using-pygithub-and-pygit2
from github import Github
from github import Auth
import pygit2

from pprint import pprint

def grab_image(url,filename):
  with urllib.request.urlopen(url) as response:
    image=Image.open(io.BytesIO(response.read()))
    image.thumbnail((config["vignette_size"],config["vignette_size"]))
    image.save(filename)

# https://stackoverflow.com/questions/287871/how-do-i-print-colored-text-to-the-terminal
def failprint(s):
  print('\x1b[1;30;41m' + s + '\x1b[0m')
def emphprint(s):
  print('\x1b[1;30;42m' + s + '\x1b[0m')
def warnprint(s):
  print('\x1b[1;30;43m' + s + '\x1b[0m')
#grab_image(image_url,"image.jpg")

# Read configurationa and assets
with open("ulsp_repo.config") as json_data:
  config = json.load(json_data)
with open("umapTemplate.json") as json_data:
  umapTemplate = json.load(json_data)
logo = Image.open("logoEle_v2.2_small.png").convert("RGBA")
master = pygit2.Repository(".")
  
# Check if repos are indicated on commandline
# If no arguments compute git diff against previous commit
diffrepos = sys.argv[1:]
if not diffrepos:
  # todo Check synchronized with remote
  for diff in master.diff("HEAD"):
    newfile = diff.delta.new_file.path
    if newfile not in (diffrepos + config["norepo_files"]) :
      diffrepos.append(os.path.splitext(newfile)[0])
# Exit if no parameters
if not diffrepos:
  emphprint("All repos in sync: no push needed")
  print("(to force push give repos as parameters)") 
else:
  # Ask confirm
  emphprint("Repos to push:")
  for r in diffrepos:
    print("\u2022 "+r)
  input("Press Enter to continue...")
  
  # Create credentials
  with Github(config["access_token"]) as g:
    try:
      user = g.get_user()
  #    pprint(user)
    except:
      failprint("Authentication failure")
      exit() 
  # Get list of repositories on github
  repos = list(map(lambda s: s.name, user.get_repos()))
  
  for reponame in diffrepos:
    ####
    # Syncing one repository
    ####  
    emphprint("\nPushing "+reponame)
    # Create if not existent
    if reponame not in repos:
      print("No " + reponame + " repo on GitHub: creating one")
      repo = user.create_repo(reponame, description = reponame + ": dataset geolocalizzato del progetto Underlandscape" )
      repo.create_file("README.md", "Create empty README", "# " + reponame)
    
    # Clone repo (after removing existent folder)
    print("Cloning repo")
    if os.path.isdir(reponame):
      shutil.rmtree(reponame, ignore_errors=True)
    clone = pygit2.clone_repository("https://github.com/prin-underlandscape/"+reponame,reponame)
    
    # Copy geojson and other related files in clone repo (excluding the cloned directory)
    related = list(filter(lambda fn: fn.startswith(reponame) and fn != reponame, os.listdir(".")))
    print("Copy files in the repository")
    for f in related:
      try:
        shutil.copyfile(f,reponame+"/"+f)
      except:
        failprint("Cannot copy file in cloned directory ("+f+")")
        exit()
    
    # Read geojson file (a FeatureCollection)
    with open(reponame+"/"+reponame+".geojson") as json_data:
      geojson = json.load(json_data)
    
    #####
    # Create pictures
    #####
    # create directory if non-existent
    print("Dowloading images into vignette folder")
    if not os.path.isdir(reponame+"/vignettes"):
      print("Creating non-existent folder for vignettes")
      os.makedirs(reponame+"/vignettes")
    
    # Scan features for pictures
    for feature in geojson["features"]:
      try:
        ulsp_type = feature["properties"]["ulsp_type"]
        if ( ulsp_type == "Percorso" ):
          url = urlparse(feature["properties"]["Foto accesso"])
        else:
          url = urlparse(feature["properties"]["Foto"])
        if ( url.netloc == 'i.postimg.cc' ):
          key = url.path.split('/')[1]
          photo_filename = reponame + "/vignettes/" + key + ".jpg"
          if ( os.path.exists(photo_filename) ):
            print(feature["properties"]["Titolo"] + " (" + feature["properties"]["ulsp_type"] +")" + ": vignette already present");
          else:
            print("Downloading vignette for " + feature["properties"]["Titolo"])
            grab_image(feature["properties"]["Foto"],photo_filename)
        else:
          if ( url.netloc != "" ):
            failprint("Invalid photo URL (not from postimages) for " + feature["properties"]["Titolo"]  + " (" + feature["properties"]["ulsp_type"] +")")
          else:
            warnprint("No photo URL for " + feature["properties"]["Titolo"]  + " (" + feature["properties"]["ulsp_type"] +")") 
      except KeyError:
        failprint("No vignette URL for " + feature["properties"]["Titolo"] + " (" + feature["properties"]["ulsp_type"] +")")
    
    ####
    # Create umap files
    ####
    print("Generate umap file")
    umap = umapTemplate
    allowed_types = list(map(lambda l: l["_umap_options"]["name"], umap["layers"]))
    for feature in geojson["features"]:
      if feature["properties"]["ulsp_type"] in allowed_types:
        feature["properties"]["_umap_options"] = {"popupTemplate": "Default"};
        layers = list(filter(lambda l: l["_umap_options"]["name"] == feature["properties"]["ulsp_type"], umap["layers"]))
        if len(layers) != 1:
          failprint("Wrong ulsp format")
        layers[0]["features"].append(feature);
    # Setup map center
        if feature["properties"]["ulsp_type"] == "POI":
          if "coordinates" not in umap:
            umap["geometry"] = {
              "type": "Point",
              "coordinates": feature["geometry"]["coordinates"]
            }
        elif feature["properties"]["ulsp_type"] == "Sito":       
          umap["geometry"] = {
            "type": "Point",
            "coordinates": feature["geometry"]["coordinates"]
          }
        else:
          umap["geometry"] = {
            "type": "Point",
            "coordinates": [10.1, 44.14]
          }
    # Setup map name
        umap["properties"]["name"] = reponame
      else:
        warnprint("Wrong ulsp_type")
    with open(reponame+"/"+reponame+".umap", 'w', encoding='utf-8') as f:
        json.dump(umap, f, ensure_ascii=False, indent=2)
    
    ####
    # Create QR codes
    ####
    print("Generate QRtags")
    logo = Image.open("logoEle_v2.2_small.png").convert("RGBA") 
    for feature in geojson["features"]:
      ulsp_type = feature["properties"]["ulsp_type"]
      if ( ulsp_type == "QRtag" ):
        if not os.path.isdir(reponame+"/qrtags"):
          print("Creating non-existent folder for qrtags")
          os.makedirs(reponame+"/qrtags")
        titolo = feature["properties"]["Titolo"]
        testo = feature["properties"]["Testo"]
        fid = feature["properties"]["fid"]
        canvas = Image.new('RGB', (960,1260), (240,240,240))
        # Logo
        logo=logo.resize((170,170))
        canvas.paste(logo, (20,1060), logo)
        # QR code
        qr = qrcode.QRCode(
          version=1,
          error_correction=qrcode.constants.ERROR_CORRECT_L,
          box_size=10,
          border=2,
        )
        testo += testo+"\n"+config["weburl"]+"/"+reponame+"/"+fid
        qr.add_data(testo)
        qr.make(fit=True)
        qrimage = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        canvas.paste(qrimage.resize((900,900)), (30,140))
        
        draw = ImageDraw.Draw(canvas)
        # Titolo
        fs=100
        line=""
        p1=""
        font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf", fs)
        for w in titolo.split(" "):
          if p1 == "":
            while font.getlength(line+" "+w) > 900:
              print(fs)
              fs -= 10
              if fs < 70:
                p1 = line
                line = ""
              font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf", fs)
          line = line+" "+w;
        titolo = line
        if p1 != "":
          titolo = p1 + "\n" + line
    #     if font.getlength(titolo) > 700:
    #       font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf", 70)
        draw.text((20, 0),titolo,(0,0,0),font)
        # Istruzioni
        font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf", 32)
        draw.text((200, 1050),"Scansiona il QR-code per maggiori informazioni\nsu questa località, anche senza usare Internet, e\ncerca altri QR-tag in quest'area",(50,50,50),font)
        # Nota
        #font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf", 32)
        #draw.text((140, 1140),"Cerca altri QR-code informativi in quest'area",(50,50,50),font)
        # Credits
        font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoMono-Regular.ttf", 28)
        draw.text((200, 1195),"Underlandscape - 2021\nProgetto di ricerca di Interesse Nazionale",(50,50,50),font)
        
        canvas.save(reponame+"/qrtags/"+fid+".png")
  
  ####
  # Create the README file
  ####
    with open(reponame+"/README.md", 'w', encoding='utf-8') as f:
      f.write("# " + reponame + "\n")
      for feature in geojson["features"]:
        ulsp_type = feature["properties"]["ulsp_type"]
        f.write("## " + feature["properties"]["ulsp_type"] + ": " + feature["properties"]["Titolo"] + "\n")
    # if qrtag display the tag
        if ( ulsp_type == "QRtag" ):
          fid = feature["properties"]["fid"]
          f.write("[<img src='qrtags/"+fid+".png' width='150'/>](qrtags/"+fid+".png) ")
    # select attribute with vignette URL
        if ( ulsp_type == "Percorso" ):
          fotourl = urlparse(feature["properties"]["Foto accesso"])
        else:
          fotourl = urlparse(feature["properties"]["Foto"])
        try:
          vignette = fotourl.path.split('/')[1]
          f.write("[<img src='vignettes/"+vignette+".jpg' width='250'/>](vignettes/"+vignette+".jpg) \n\n")
        except IndexError:
          warnprint("No vignette for "+ feature["properties"]["ulsp_type"] + " " + feature["properties"]["Titolo"])
          f.write("*Nessuna immagine* \n\n")
        f.write("**"+feature["properties"]["Descrizione"]+"**"+"\n")
    # Build index and tree
    clone.index.add_all()
    clone.index.write()
    tree = clone.index.write_tree()
    # Commit
    author = pygit2.Signature("Augusto Ciuffoletti", "augusto.ciuffoletti@gmail.com")
    oid = clone.create_commit('refs/heads/main', author, author, "new commit",tree,[clone.head.target])
    # Build credentials
    credentials = pygit2.UserPass(config["username"], config["access_token"])
    # Push on "origin" remote with user credentials
    remote = clone.remotes["origin"]
    remote.credentials = credentials
    callbacks=pygit2.RemoteCallbacks(credentials=credentials)
    remote.push(['refs/heads/main'],callbacks=callbacks)
    # Remove repository directory
    shutil.rmtree(reponame, ignore_errors=True)

###
# Commit master repository 
###
# Build index and tree
master.index.add_all()
master.index.write()
tree = master.index.write_tree()
# Commit
author = pygit2.Signature("Augusto Ciuffoletti", "augusto.ciuffoletti@gmail.com")
message = input("Enter commit message: ")
master.create_commit('refs/heads/master', author, author, message,tree,[master.head.target])
# Build credentials
credentials = pygit2.UserPass(config["username"], config["access_token"])
# Push on "origin" remote with user credentials
remote = master.remotes["origin"]
remote.credentials = credentials
callbacks=pygit2.RemoteCallbacks(credentials=credentials)
remote.push(['refs/heads/master'],callbacks=callbacks)

