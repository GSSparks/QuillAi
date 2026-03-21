{
  description = "QuillAI - A Privacy-First IDE";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      # Support for standard 64-bit Linux (NixOS)
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      python = pkgs.python3;
      pythonPackages = python.pkgs;
    in
    {
      packages.${system}.default = pythonPackages.buildPythonApplication {
        pname = "quillai";
        version = "1.0.0";

        # We tell Nix we are handling the install phase manually since we don't have a setup.py
        format = "other";

        src = ./.;

        # These hooks magically fix Qt6 themes, plugins, and Wayland/X11 scaling on NixOS
        nativeBuildInputs = [
          pkgs.qt6.wrapQtAppsHook
          pkgs.makeWrapper
        ];

        # The Python libraries QuillAI needs to run
        propagatedBuildInputs = with pythonPackages; [
          pyqt6
          pyyaml
          requests # <--- [FIXED] Added requests here!
        ];

        # Ensure Wayland support is bundled for modern Linux desktops
        buildInputs = [
          pkgs.qt6.qtwayland
        ];

        installPhase = ''
          # Create the output directories
          mkdir -p $out/bin
          mkdir -p $out/share/quillai
          
          # Copy your entire Python project into the Nix store
          cp -r * $out/share/quillai/
          
          # Create the executable wrapper
          makeWrapper ${python.interpreter} $out/bin/quillai \
            --add-flags "$out/share/quillai/main.py" \
            --set PYTHONPATH "$PYTHONPATH:$out/share/quillai" \
            --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.git python ]}
        '';

        # Ensure the Qt hook processes our newly created executable
        dontWrapQtApps = false; 
      };

      # Allow running the app directly via `nix run`
      apps.${system}.default = {
        type = "app";
        program = "${self.packages.${system}.default}/bin/quillai";
      };
    };
}