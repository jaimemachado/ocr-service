{
  description = "Development shell for ocr-service";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };
  outputs = { self, nixpkgs, ... }:
  let
    systems = [ "x86_64-linux" "aarch64-linux" ];
  in
  {
    devShells = builtins.listToAttrs (map (system: {
      name = system;
      value = let pkgs = import nixpkgs { inherit system; }; in {
        default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python311
            git
            gcc
            pkg-config
            stdenv.cc.cc.lib
            zlib
            # OpenGL and graphics libraries for OpenCV
            libGL
            libGLU
            glib
            xorg.libX11
            xorg.libXext
            # Text rendering libraries for matplotlib/doctr
            pango
            cairo
            gdk-pixbuf
            fontconfig
            freetype
          ];

          shellHook = ''
            # Add libraries to LD_LIBRARY_PATH
            export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [
              pkgs.stdenv.cc.cc.lib
              pkgs.zlib
              pkgs.libGL
              pkgs.libGLU
              pkgs.glib
              pkgs.xorg.libX11
              pkgs.xorg.libXext
              pkgs.pango
              pkgs.cairo
              pkgs.gdk-pixbuf
              pkgs.fontconfig
              pkgs.freetype
            ]}:$LD_LIBRARY_PATH"

            if [ -f requirements.txt ]; then
              if [ ! -d .venv ]; then
                python -m venv .venv
                . .venv/bin/activate
                python -m pip install --upgrade pip
                pip install -r requirements.txt
              else
                . .venv/bin/activate
              fi
            else
              echo "Warning: requirements.txt not found; no Python deps installed." >&2
            fi
          '';
        };
      };
    }) systems);
  };
}