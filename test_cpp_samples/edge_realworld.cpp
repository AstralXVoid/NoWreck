// edge_realworld.cpp — a realistic mix of the shapes above.

#include <map>

namespace tokenizer
{
    class Scanner
    {
    public:
        Scanner(const std::string& input) : input_(input), pos_(0) {}

        char peek() const
        {
            return input_[pos_];
        }

        bool done() const
        {
            return pos_ >= input_.size();
        }

        std::string next_token()
        {
            skip_whitespace();
            return read_word();
        }

    private:
        void skip_whitespace()
        {
            while (!done() && peek() == ' ')
            {
                advance();
            }
        }

        std::string read_word()
        {
            std::string word;
            while (!done() && peek() != ' ')
            {
                word.push_back(peek());
                advance();
            }
            return word;
        }

        void advance();
        void report(const std::string& message);

        std::string input_;
        std::size_t pos_;
    };

    std::string normalise(const std::string& text)
    {
        Scanner scanner(text);
        return scanner.next_token();
    }
}

std::string tokenize(const std::string& input)
{
    return tokenizer::normalise(input);
}
