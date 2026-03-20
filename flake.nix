{
  description = "Coding Notepad with PyQt6 and local LLM support";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        pythonEnv = pkgs.python310.withPackages (ps: with ps; [
          pyqt6
          requests
          pyqt6-sip
          # Optional: for fancy editor features
          pygments
        ]);
      in {
        devShell = pkgs.mkShell {
          name = "coding-notepad-shell";
          buildInputs = [ pythonEnv ];
          shellHook = ''
            echo "Welcome to the Coding Notepad dev environment!"
            echo "Run your editor with: python main.py"
          '';
        };

        # Optional: provide a simple runnable package
        packages.notepad = pkgs.stdenv.mkDerivation {
          pname = "coding-notepad";
          version = "0.1";
          src = ./.;
          buildInputs = [ pythonEnv ];
          dontBuild = true;
          installPhase = ''
            mkdir -p $out
            cp -r * $out/
          '';
        };
      }
    );
}
