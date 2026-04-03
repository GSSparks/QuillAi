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

      # ── Language servers ───────────────────────────────────────────
      lspServers = [
        pythonPackages.python-lsp-server
        pkgs.nodePackages.yaml-language-server
        pkgs.nodePackages.typescript-language-server
        pkgs.nodePackages.bash-language-server
        pkgs.nodePackages.vscode-langservers-extracted
        pkgs.nil
        pkgs.lua-language-server
        pkgs.perlnavigator
      ];

      quillaiDesktop = pkgs.makeDesktopItem {
        name        = "quillai";
        desktopName = "QuillAI";
        comment     = "A Privacy-First Python IDE";
        exec        = "quillai";
        icon        = "quillai_logo_min";
        terminal    = false;
        categories  = [ "Development" "IDE" "TextEditor" ];
      };

    in
    {
      packages.${system}.default = pythonPackages.buildPythonApplication {
        pname   = "quillai";
        version = "1.0.0";
        format  = "other";
        src     = ./.;
        dontBuild = true;

        nativeBuildInputs = [
          pkgs.qt6.wrapQtAppsHook
          pkgs.qt6.qtbase
          pkgs.makeWrapper
          pkgs.copyDesktopItems
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
          perlnavigator
          chromadb
          sentence-transformers
          # sentence-transformers and chromadb are optional —
          # torch's build requirements conflict with the Nix sandbox.
          # Install manually if you want vector indexing:
          #   pip install sentence-transformers chromadb
        ];

        buildInputs = [
          pkgs.qt6.qtwayland
          pkgs.qt6.qtbase
          pkgs.shellcheck
        ] ++ lspServers;

        desktopItems = [ quillaiDesktop ];

        installPhase = ''
          runHook preInstall

          mkdir -p $out/bin
          mkdir -p $out/share/quillai
          mkdir -p $out/share/icons/hicolor/scalable/apps

          cp -r * $out/share/quillai/
          cp images/quillai_logo_min.svg \
            $out/share/icons/hicolor/scalable/apps/quillai_logo_min.svg

          makeWrapper ${python.interpreter} $out/bin/quillai \
            --add-flags "$out/share/quillai/main.py" \
            --set PYTHONPATH "$PYTHONPATH:$out/share/quillai" \
            --prefix PATH : ${pkgs.lib.makeBinPath ([
              pkgs.git
              python
              pkgs.shellcheck
            ] ++ lspServers)}

          runHook postInstall
        '';

        dontWrapQtApps = false;
      };

      apps.${system}.default = {
        type    = "app";
        program = "${self.packages.${system}.default}/bin/quillai";
      };

      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          (python.withPackages (ps: with ps; [
            pyqt6
            pyyaml
            requests
            markdown
            pygments
            python-lsp-server
            sentence-transformers
            chromadb
          ]))
          pkgs.qt6.qtbase
          pkgs.qt6.qtwayland
          pkgs.shellcheck
          pkgs.git
          pkgs.inter
          pkgs.jetbrains-mono
          pkgs.perlnavigator
        ] ++ lspServers;

        shellHook = ''
          export PYTHONPATH="$PWD:$PYTHONPATH"
          export QT_QPA_PLATFORM=wayland

          echo "QuillAI dev shell ready — $(python --version)"
          echo ""
          echo "Language servers:"
          for srv in \
            pylsp \
            yaml-language-server \
            typescript-language-server \
            bash-language-server \
            vscode-html-language-server \
            vscode-css-language-server \
            vscode-json-language-server \
            vscode-markdown-language-server \
            nil \
            perlnavigator \
            lua-language-server; do
            if command -v "$srv" &>/dev/null; then
              echo "  ✓ $srv"
            else
              echo "  ✗ $srv"
            fi
          done
          echo ""
          echo "Vector index:"
          python -c "from sentence_transformers import SentenceTransformer; print('  ✓ sentence-transformers')" 2>/dev/null || echo "  ✗ sentence-transformers"
          python -c "import chromadb; print('  ✓ chromadb')" 2>/dev/null || echo "  ✗ chromadb"
        '';
      };
    };
}