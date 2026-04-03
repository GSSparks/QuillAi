#!/usr/bin/env perl
# test_quillai.pl — QuillAI Perl feature test

use strict;
use warnings;
use feature 'say';

# ── Package / class definition ────────────────────────────────────────────────

package Animal;

sub new {
    my ($class, %args) = @_;
    return bless {
        name  => $args{name}  // 'Unknown',
        sound => $args{sound} // 'silence',
        legs  => $args{legs}  // 4,
    }, $class;
}

sub speak {
    my $self = shift;
    printf "%s says %s\n", $self->{name}, $self->{sound};
}

sub describe {
    my $self = shift;
    return sprintf "%s has %d legs", $self->{name}, $self->{legs};
}

# ── Subclass ──────────────────────────────────────────────────────────────────

package Dog;
use parent -norequire, 'Animal';

sub new {
    my ($class, %args) = @_;
    $args{sound} = 'woof';
    my $self = $class->SUPER::new(%args);
    return $self;
}

sub fetch {
    my ($self, $item) = @_;
    say "$self->{name} fetches the $item!";
}

# ── Main script ───────────────────────────────────────────────────────────────

package main;

# Scalars, arrays, hashes
my $greeting  = "Hello from QuillAI";
my @colors    = ('red', 'green', 'blue');
my %capitals  = (
    France  => 'Paris',
    Germany => 'Berlin',
    Japan   => 'Tokyo',
);

say $greeting;

# Array operations
push @colors, 'yellow';
my $count = scalar @colors;
say "Colors: " . join(', ', @colors) . " ($count total)";

# Hash operations
while (my ($country, $capital) = each %capitals) {
    printf "%-10s => %s\n", $country, $capital;
}

# Control flow
foreach my $color (@colors) {
    if ($color eq 'red') {
        say "Found red!";
    } elsif ($color eq 'blue') {
        say "Found blue!";
    } else {
        say "Other color: $color";
    }
}

# Regex
my $text = "The quick brown fox jumps over the lazy dog";
if ($text =~ /(\w+)\s+fox/) {
    say "Word before fox: $1";
}

(my $clean = $text) =~ s/\b(\w)/uc($1)/ge;
say "Title case: $clean";

# References
my $matrix = [[1,2,3],[4,5,6],[7,8,9]];
for my $row (@$matrix) {
    say join(' ', @$row);
}

# Subroutine refs and map/grep
my @numbers  = (1..10);
my @evens    = grep { $_ % 2 == 0 } @numbers;
my @doubled  = map  { $_ * 2 }      @evens;
say "Doubled evens: " . join(', ', @doubled);

# Objects
my $dog = Dog->new(name => 'Rex', legs => 4);
$dog->speak;
$dog->fetch('ball');
say $dog->describe;

# Special variables
say "Script name: $0";
say "Process ID:  $$";

# Error handling
eval {
    die "Something went wrong!\n";
};
if ($@) {
    warn "Caught error: $@";
}

# Heredoc
my $heredoc = <<END;
This is a heredoc.
It spans multiple lines.
Name: ${\$dog->{name}}
END
print $heredoc;

say "Done!";