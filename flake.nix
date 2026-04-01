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
        icon = "quillai_logo_min";
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
          pkgs.qt6.qtbase
          pkgs.makeWrapper
          pkgs.copyDesktopItems # Nix hook to automatically install desktop items
          pkgs.inter
          pkgs.jetbrains-mono
          pkgs.wget
        ];

        propagatedBuildInputs = with pythonPackages; [
          pyqt6
          pyyaml
          requests
          markdown
          pygments
          python-lsp-server
        ];

        buildInputs = [
          pkgs.qt6.qtwayland
          pkgs.qt6.qtbase
          pkgs.shellcheck
        ];

        # Tell the hook which desktop item to build and place in /share/applications/
        desktopItems = [ quillaiDesktop ];

        installPhase = ''
          runHook preInstall
        
          mkdir -p $out/bin
          mkdir -p $out/share/quillai
          mkdir -p $out/share/icons/hicolor/scalable/apps
        
          cp -r * $out/share/quillai/
          cp images/quillai_logo_min.svg $out/share/icons/hicolor/scalable/apps/quillai_logo_min.svg
        
          makeWrapper ${python.interpreter} $out/bin/quillai \
            --add-flags "$out/share/quillai/main.py" \
            --set PYTHONPATH "$PYTHONPATH:$out/share/quillai" \
            --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.git python pkgs.shellcheck pythonPackages.python-lsp-server ]}
        
          runHook postInstall
        '';

        dontWrapQtApps = false; 
      };

      apps.${system}.default = {
        type = "app";
        program = "${self.packages.${system}.default}/bin/quillai";
      };
      
      # ── Dev shell ──────────────────────────────────────────────────
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          # Python with all deps in one interpreter
          (python.withPackages (ps: with ps; [
            pyqt6
            pyyaml
            requests
            markdown
            pygments
            python-lsp-server 
          ]))
        
          # System tools
          pkgs.qt6.qtbase
          pkgs.qt6.qtwayland
          pkgs.shellcheck
          pkgs.git
          pkgs.inter
          pkgs.jetbrains-mono
        ];
        
        shellHook = ''
          export PYTHONPATH="$PWD:$PYTHONPATH"
          export QT_QPA_PLATFORM=wayland
          echo "QuillAI dev shell ready — python $(python --version)"
          echo "pylsp: $(pylsp --version)"
        '';
      };
    };
    
}