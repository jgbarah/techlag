# TechLag

Scripts and info for this idea about technical lag in software compilations

## Upstream more likely commit

We can assume that source packages in software compilations (downstream packages) are derived from some upstream package. In this case, we have the problem of finding from which version of the upstream package is derived an specific downstream package. Or more exactly, which is the closest version of the upstream package to the given downstream. If upstream packages are maintained in git repositories, the problem is then finding the most likely upstream commit from which the downstream package is derived.

For estimating the most likely upstream commit for a given downstream package, we can compare each upstream checkout (for all its commits) to the downstream package. To simplify things a bit, we can assume that we're interested in finding this commit in the upstream master branch. To make the search more efficient, the estimation will be done by successive approximations,


## Installation

Ensure Python 3.x (at least 3.4) is installed. The debian-source utility is needed too for programs dealing with Debian packages. In Debian systems, you can install it by:

```
apt-get install debian-dev
```

Then, install the Python dependencies. Next instructions are for using virtualenv and pip, but they can be easily adapted to other procedures:

```
$ virtualenv -p /usr/bin/python3 ~/venv-techlag
$ source ~/venb-techlag/bin/activate
(venv-techlag) $ git clone http://github.com/jgbarah/techlag.git
(venv-techlag) $ cd techlag
(venv-techlag) $ pip install -r requirements.txt
(venv-techlag) $ python3 setup.sh install
```

After this, the programs and libraries provided by techlag are installed in the virtualenv. To work with them, remember to activate the envirionment in the shell where you intend to run the programs or use the libraries.

## Examples

Some examples on how to run the script for finding the most likely upstream commit:

* For comparing the source directory `git-2.7.0` with the git repository `git.repo`, assuming the most likely commit was authored after 2016-02-01, and using a step of 10 (test every 10 commmits) for a start.

```
gitlag --repo git.repo -p git-2.7.0 --after 2016-02-01 --step 10 -l info
```

* For comparing the source Debian package `git`, as found in the Debian repository for the `stretch/main` release, assuming the most likely commit was authored after 2016-02-01, and using a step of 10 (test every 10 commmits) for a start. Store the output (a line describing the most likely commit) in `/tmp/diff-git.output`:

```
gitlag --debian_name git stretch/main --repo git.repo --after 2016-02-01 \
  --step 10 -l info > /tmp/diff-git.output
```

* For comparing the source Debian package `git`, as found in the Debian repositories for the `jessie/main`, `stretch/main`, `wheezy/main`, and `sid/main` releases, assuming the most likely commit was authored after 2014-02-01, and using a step of 10 (test every 10 commmits) for a start. Store the output (a line describing the most likely commit) in `/tmp/diff-git.output`:

```
gitlag --debian_name git jessie/main stretch/main wheezy/main sid/main \
  --repo git.repo --after 2014-02-01 --step 10 -l info > /tmp/diff-git.output
```

* Similar, but now obtaining a CSV with the commits tested, for verification (see sample of that below):

```
bin/gitlag --debian_name git stretch/main jessie/main wheezy/main sid/main \
  --repo git.repo --after 2000-06-27 --steps 10 -l info \
  > /tmp/diff-git-10.output 2> /tmp/diff-git-10.debug

grep INFO:CSV /tmp/diff-git-10.debug > /tmp/diff-git-10.csv
```

The file /tmp/diff-git-10.csv/tmp/diff-git-10.csv is like this:

```
INFO:CSV,git:stretch/main,commit_seq,date,total_lines,total_files,added_lines,removed_lines
INFO:CSV,git:stretch/main,        0,Thu Apr 7 15:13:13 2005 -0700,   172033,   407,     6648,      297
INFO:CSV,git:stretch/main,     4330,Wed Apr 26 17:08:00 2006 -0700,   432267,  1750,    91190,    27270
INFO:CSV,git:stretch/main,     4331,Wed Apr 26 17:16:11 2006 -0700,   432275,  1750,    91190,    27270
INFO:CSV,git:stretch/main,     4332,Wed Apr 26 17:23:51 2006 -0700,   432340,  1756,    91365,    27397
INFO:CSV,git:stretch/main,     4333,Wed Apr 26 17:10:33 2006 -0700,   432259,  1750,    91154,    27298
INFO:CSV,git:stretch/main,     8660,Fri Feb 23 00:57:12 2007 -0800,   469812,  1984,   138915,    50648
INFO:CSV,git:stretch/main,     8662,Fri Feb 23 00:57:12 2007 -0800,   469853,  1984,   139009,    50709
INFO:CSV,git:stretch/main,     8664,Fri Feb 23 00:57:12 2007 -0800,   469974,  1984,   139009,    50830
...
```

## Checking technical lag for Debian Snapshot pacakges

```
debsnapshotlag -c snapshot.json --store debsnapshot-store -l info \
   > debsnapshot.log 2> debsnapshot-err.log
```
