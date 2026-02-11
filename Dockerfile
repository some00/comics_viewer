FROM archlinux:latest
RUN pacman -Sy --noconfirm base-devel fakeroot git wget python-virtualenv cairo
RUN useradd -m tkonya && usermod -aG wheel tkonya
RUN echo '%wheel ALL=(ALL:ALL) NOPASSWD: ALL' >> /etc/sudoers.d/wheel.conf
USER tkonya
WORKDIR /tmp/
RUN wget https://aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h=pyrefly-bin &&\
    mv 'PKGBUILD?h=pyrefly-bin' PKGBUILD && \
    makepkg -s --noconfirm
USER root
RUN pacman -U --noconfirm /tmp/*.pkg.tar.zst
USER tkonya
WORKDIR /mnt

