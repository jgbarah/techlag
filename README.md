# TechLag

Scripts and info for this idea about technical lag in software compilations

## Upstream more likely commit

We can assume that source packages in software compilations (downstream packages) are derived from some upstream package. In this case, we have the problem of finding from which version of the upstream package is derived an specific downstream package. Or more exactly, which is the closest version of the upstream package to the given downstream. If upstream packages are maintained in git repositories, the problem is then finding the most likely upstream commit from which the downstream package is derived.

For estimating the most likely upstream commit for a given downstream package, we can compare each upstream checkout (for all its commits) to the downstream package. To simplify things a bit, we can assume that we're interested in finding this commit in the upstream master branch. To make the search more efficient, the estimation will be done by successive approximations,

### Examples

Some examples on how to run the script for finding the most likely upstream commit:

* For comparing the source directory `git-2.7.0` with the git repository `git.repo`, assuming the most likely commit was authored after 2016-02-01, and using a step of 10 (test every 10 commmits) for a start.

```
gitlag.py --repo git.repo -p git-2.7.0 --after 2016-02-01 --step 10 -l info
```

* For comparing the source Debian package `git`, as found in the Debian repository for the `stretch/main` release , assuming the most likely commit was authored after 2016-02-01, and using a step of 10 (test every 10 commmits) for a start. Store the output (a line describing the most likely commit) in `/tmp/diff-git.output`:

```
gitlag.py --debian_name git stretch/main --repo git.repo --after 2016-02-01 --step 10 -l info > /tmp/diff-git.output
```
