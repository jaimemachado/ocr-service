{
  description = "Development shell for ocr-service";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };

  outputs = { self, nixpkgs, ... }:
  let
    system = builtins.currentSystem;
    pkgs = import nixpkgs { inherit system; };
  in {
    devShells.${system}.default = pkgs.mkShell {
      buildInputs = with pkgs; [ python311 git gcc pkg-config ];

      # Create/activate a local virtualenv and install requirements.txt
      shellHook = ''
        if [ -f requirements.txt ]; then
          # Create a reproducible local venv for developer convenience
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
}
