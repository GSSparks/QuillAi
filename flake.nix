{
  description = "QuillAI - A Privacy-First IDE";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      python = pkgs.python3;
      pythonPackages = python.pkgs;

      # Define the Desktop Application Entry
      quillaiDesktop = pkgs.makeDesktopItem {
        name = "quillai";
        desktopName = "QuillAI";
        comment = "A Privacy-First Python IDE";
        exec = "quillai";
        icon = "accessories-text-editor"; # Standard generic text editor icon
        terminal = false;
        categories = [ "Development" "IDE" "TextEditor" ];
      };

    in
    {
      packages.${system}.default = pythonPackages.buildPythonApplication {
        pname = "quillai";
        version = "1.0.0";

        format = "other";

        src = ./.;

        nativeBuildInputs = [
          pkgs.qt6.wrapQtAppsHook
          pkgs.makeWrapper
          pkgs.copyDesktopItems # [NEW] Nix hook to automatically install desktop items
        ];

        propagatedBuildInputs = with pythonPackages; [
          pyqt6
          pyyaml
          requests
        ];

        buildInputs = [
          pkgs.qt6.qtwayland
          pkgs.shellcheck
        ];

        # [NEW] Tell the hook which desktop item to build and place in /share/applications/
        desktopItems = [ quillaiDesktop ];

        installPhase = ''
          mkdir -p $out/bin
          mkdir -p $out/share/quillai
          
          cp -r * $out/share/quillai/
          
          makeWrapper ${python.interpreter} $out/bin/quillai \
            --add-flags "$out/share/quillai/main.py" \
            --set PYTHONPATH "$PYTHONPATH:$out/share/quillai" \
            --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.git python ]}
        '';

        dontWrapQtApps = false; 
      };

      apps.${system}.default = {
        type = "app";
        program = "${self.packages.${system}.default}/bin/quillai";
      };
    };
}