FROM archlinux:latest
RUN pacman -Sy --noconfirm base-devel fakeroot git wget python-virtualenv \
        cairo unrar uv gtk3 gobject-introspection-runtime
RUN useradd -m build && usermod -aG wheel build
USER build
WORKDIR /tmp/
RUN wget https://aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h=pyrefly-bin &&\
    mv 'PKGBUILD?h=pyrefly-bin' PKGBUILD && \
    makepkg -s --noconfirm
USER root
RUN pacman -U --noconfirm /tmp/*.pkg.tar.zst
USER build
WORKDIR /mnt
