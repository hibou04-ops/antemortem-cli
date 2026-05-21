# symlink_escape_citation

The fixture repo contains a link inside `repo/src` that points outside the repo
root. On Windows this fixture uses a directory junction because file symlink
creation requires elevated privileges. Citation verification must resolve the
final path and reject the escape instead of trusting the link location.
